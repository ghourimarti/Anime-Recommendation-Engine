# apps/web

Next.js (App Router) frontend — the streaming query UX and Clerk auth. It talks
to the API through same-origin route handlers (`src/app/api/*`) that attach the
Clerk token server-side, so the backend URL and token never reach the browser.

```bash
pnpm install
pnpm dev          # http://localhost:3000
pnpm typecheck && pnpm lint && pnpm test
```
