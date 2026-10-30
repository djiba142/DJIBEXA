export function renderErrorPage(): string {
  return `<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <title>Cette page n'a pas pu se charger</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { font: 15px/1.5 system-ui, -apple-system, sans-serif; background: #fafafa; color: #111; display: grid; place-items: center; min-height: 100vh; margin: 0; padding: 1.5rem; }
      .card { max-width: 28rem; width: 100%; text-align: center; padding: 2rem; }
      h1 { font-size: 1.25rem; margin: 0 0 0.5rem; }
      p { color: #4b5563; margin: 0 0 1.5rem; }
      .actions { display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; }
      a, button { padding: 0.5rem 1rem; border-radius: 0.375rem; font: inherit; cursor: pointer; text-decoration: none; border: 1px solid transparent; }
      .primary { background: #111; color: #fff; }
      .secondary { background: #fff; color: #111; border-color: #d1d5db; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1 id="error-title">Cette page n'a pas pu se charger</h1>
      <p id="error-description">Une erreur est survenue. Vous pouvez réessayer ou retourner à l'accueil.</p>
      <div class="actions">
        <button id="error-retry" class="primary" onclick="location.reload()">Réessayer</button>
        <a id="error-home" class="secondary" href="/">Accueil</a>
      </div>
    </div>
    <script>
      const messages = {
        fr: {
          title: "Cette page n'a pas pu se charger",
          description: "Une erreur est survenue. Vous pouvez réessayer ou retourner à l'accueil.",
          retry: "Réessayer",
          home: "Accueil",
        },
        en: {
          title: "This page didn't load",
          description: "Something went wrong. You can try again or go back home.",
          retry: "Try again",
          home: "Go home",
        },
        ar: {
          title: "تعذر تحميل هذه الصفحة",
          description: "حدث خطأ ما. يمكنك المحاولة مرة أخرى أو العودة إلى الصفحة الرئيسية.",
          retry: "إعادة المحاولة",
          home: "الرئيسية",
        },
        zh: {
          title: "此页面无法加载",
          description: "发生了错误。您可以重试或返回首页。",
          retry: "重试",
          home: "返回首页",
        },
      };
      let savedLanguage;
      try {
        savedLanguage = JSON.parse(localStorage.getItem("kap-settings") || "{}").language;
      } catch {
        savedLanguage = undefined;
      }
      const browserLanguage = navigator.language.toLowerCase().split("-")[0];
      const language = Object.hasOwn(messages, savedLanguage)
        ? savedLanguage
        : Object.hasOwn(messages, browserLanguage)
          ? browserLanguage
          : "fr";
      const text = messages[language];
      document.documentElement.lang = language;
      document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
      document.title = text.title;
      document.getElementById("error-title").textContent = text.title;
      document.getElementById("error-description").textContent = text.description;
      document.getElementById("error-retry").textContent = text.retry;
      document.getElementById("error-home").textContent = text.home;
    </script>
  </body>
</html>`;
}
