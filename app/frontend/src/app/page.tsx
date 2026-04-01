import { ApiStatus } from "@/components/ApiStatus";

export default function Home() {
  return (
    <div className="min-h-screen bg-zinc-50 font-sans text-zinc-900 dark:bg-black dark:text-zinc-50">
      <main className="mx-auto flex max-w-2xl flex-col gap-8 px-6 py-16">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-zinc-500">
            Fashion Garment
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">
            Inspiration library
          </h1>
          <p className="mt-4 text-lg leading-relaxed text-zinc-600 dark:text-zinc-400">
            Uploads, AI garment metadata, search, and designer annotations will
            live here. This page confirms the Next.js frontend can talk to the
            FastAPI backend.
          </p>
        </div>
        <ApiStatus />
      </main>
    </div>
  );
}
