from io import BytesIO
from pathlib import Path

from asn1crypto import pem, x509
from django.conf import settings
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import signers
from pyhanko.sign.timestamps import HTTPTimeStamper
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext


class InvoiceSigningError(Exception):
    pass


def _load_trust_root():
    trust_root_path = settings.PDF_SIGNING_TRUST_ROOT_PATH
    if not trust_root_path:
        raise InvoiceSigningError('Le certificat racine de confiance PDF n’est pas configuré.')
    try:
        certificate_bytes = Path(trust_root_path).read_bytes()
        if pem.detect(certificate_bytes):
            _, _, certificate_bytes = pem.unarmor(certificate_bytes)
        return x509.Certificate.load(certificate_bytes)
    except Exception as exc:
        raise InvoiceSigningError('Le certificat racine de confiance PDF est invalide.') from exc


def _validate_signature(signed_pdf):
    trust_root = _load_trust_root()
    reader = PdfFileReader(BytesIO(signed_pdf))
    if len(reader.embedded_signatures) != 1:
        raise InvoiceSigningError('La signature PDF est absente ou ambiguë.')
    validation = validate_pdf_signature(
        reader.embedded_signatures[0],
        signer_validation_context=ValidationContext(
            trust_roots=[trust_root],
            allow_fetching=False,
            revocation_mode=settings.PDF_SIGNING_REVOCATION_MODE,
        ),
    )
    if not (
        validation.intact
        and validation.valid
        and validation.trusted
        and validation.bottom_line
    ):
        raise InvoiceSigningError('La vérification cryptographique ou la confiance du certificat a échoué.')
    return validation


def sign_and_verify_pdf(unsigned_pdf):
    pkcs12_path = settings.PDF_SIGNING_PKCS12_PATH
    if not pkcs12_path or not Path(pkcs12_path).is_file():
        raise InvoiceSigningError('Aucun certificat de signature PDF n’est configuré.')

    try:
        signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=pkcs12_path,
            passphrase=settings.PDF_SIGNING_PKCS12_PASSPHRASE.encode() or None,
        )
        if signer is None:
            raise InvoiceSigningError('Le certificat PKCS#12 ne contient pas de clé de signature.')

        timestamper = HTTPTimeStamper(settings.PDF_TSA_URL) if settings.PDF_TSA_URL else None
        signature_metadata = signers.PdfSignatureMetadata(
            field_name='KAPInvoiceSignature',
            md_algorithm='sha256',
            reason='Émission de facture KOUROUMA AUTO PART',
            location='Conakry, Guinée',
        )
        output = BytesIO()
        signers.PdfSigner(
            signature_metadata,
            signer=signer,
            timestamper=timestamper,
        ).sign_pdf(IncrementalPdfFileWriter(BytesIO(unsigned_pdf)), output=output)
        signed_pdf = output.getvalue()
        _validate_signature(signed_pdf)
        return signed_pdf
    except InvoiceSigningError:
        raise
    except Exception as exc:
        raise InvoiceSigningError(
            f'La signature PDF ou son contrôle a échoué ({type(exc).__name__}: {exc}).'
        ) from exc


def verify_signed_pdf(signed_pdf):
    try:
        _validate_signature(signed_pdf)
        return True
    except InvoiceSigningError:
        return False