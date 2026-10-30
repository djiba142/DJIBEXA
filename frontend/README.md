# Kourouma Auto Part

Interface de gestion commerciale connectée au backend Django REST du dépôt.

## Prérequis

- Node.js et npm
- Python et les dépendances du backend Django

## Configuration

Le frontend utilise par défaut l'API `http://127.0.0.1:8000/api/v1`. Pour une autre adresse,
définissez `VITE_API_BASE_URL` dans l'environnement du frontend.

L'authentification repose sur les sessions Django. Le backend doit autoriser l'origine du frontend
avec les cookies CORS et CSRF activés.

## Développement

Démarrez d'abord le backend depuis `../backend` :

```sh
python manage.py migrate
python manage.py runserver
```

Puis dans ce dossier :

```sh
npm install
npm run dev
```

Pour vérifier la version de production :

```sh
npm run build
```
