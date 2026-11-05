"""Windows executable entry point; keep package-relative imports inside the package."""

from fanqie_short_story.web import main


if __name__ == "__main__":
    raise SystemExit(main())
