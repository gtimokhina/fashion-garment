import Link from "next/link";

const link =
  "text-sm font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100";

export function Nav() {
  return (
    <header className="border-b border-zinc-200 bg-white/80 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/80">
      <nav className="mx-auto flex max-w-4xl items-center gap-6 px-6 py-3">
        <Link href="/" className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Fashion Garment
        </Link>
        <div className="flex gap-5">
          <Link href="/upload" className={link}>
            Upload
          </Link>
        </div>
      </nav>
    </header>
  );
}
