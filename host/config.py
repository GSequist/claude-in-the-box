SKIP_DIRS = [
    ".claude/",  # Claude config/skills
    "node_modules/",  # npm packages
    "venv/",
    ".venv/",
    "env/",  # Python venvs
    "__pycache__/",  # Python cache
    ".git/",  # Git repo
    ".next/",  # Next.js build cache
    ".nuxt/",  # Nuxt.js build cache
    ".svelte-kit/",  # SvelteKit build
    ".turbo/",  # Turborepo cache
    "dist/",
    "build/",  # Build outputs
    "out/",  # Next.js static export
    "public/",  # Static assets (often large)
    ".pytest_cache/",  # Pytest cache
    ".mypy_cache/",  # Mypy cache
    ".ruff_cache/",  # Ruff linter cache
    "htmlcov/",  # Coverage reports
    ".coverage/",  # Coverage data
    "vendor/",  # Go/PHP dependencies
    "target/",  # Rust/Java build
    ".gradle/",  # Gradle cache
    ".cargo/",  # Rust cargo cache
    ".npm/",  # npm cache
    ".yarn/",  # Yarn cache
    ".pnp/",  # Yarn PnP
    "tmp/",
    "temp/",  # Temporary directories
]

SKIP_FILES = [
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    ".DS_Store",  # macOS metadata
    "Thumbs.db",  # Windows thumbnails
    ".env",  # Environment variables (sensitive)
    ".env.local",
    ".env.production",
    "tsconfig.tsbuildinfo",  # TypeScript incremental build
    "*.log",  # Log files
    "npm-debug.log",
    "yarn-debug.log",
    "yarn-error.log",
]
