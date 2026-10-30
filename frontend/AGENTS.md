# Image & Ad Studio

This frontend uses TanStack Start and the Django REST API in `../backend`.

- Configure `VITE_API_BASE_URL` to point to the backend API root (default: `http://127.0.0.1:8000/api/v1`).
- Django session authentication requires browser cookies and CSRF tokens; use the shared API client in `src/lib/api.ts`.
- Run the frontend with `npm run dev` and create a production build with `npm run build`.
