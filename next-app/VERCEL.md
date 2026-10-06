# Deploying to Vercel

Step-by-step instructions to deploy this Next.js app to Vercel.

## Option 1: Deploy via Vercel Dashboard (Easiest)

1. Push your repository to GitHub.
2. Go to [vercel.com](https://vercel.com) and click **"Add New Project"**.
3. Import your repository: `kusunz/ImageToTextStreamlit`.
4. In the **"Root Directory"** setting, select or enter `next-app`.
5. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`: Your Gemini API key from [aistudio.google.com](https://aistudio.google.com/apikey).
   - `POSTGRES_URL` (Optional): Connection string for Vercel Postgres, Neon, or Supabase.
6. Click **Deploy**. Vercel will build and assign a global HTTPS domain in ~45 seconds.

## Option 2: Deploy via Vercel CLI

```bash
cd next-app
npm i -g vercel
vercel
```

Follow the prompts and link your project. Then deploy to production:

```bash
vercel --prod
```

## Features on Vercel

- **Global CDN Delivery**: Lightning-fast initial page loads (<50ms).
- **Serverless API Routes**: Vision extraction runs with automatic horizontal scaling and up to 60s timeout.
- **Zero-Config Database**: Works out-of-the-box with in-memory store or connects seamlessly with Vercel Postgres / Neon.
