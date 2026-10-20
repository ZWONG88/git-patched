from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "backend"
DESTINATION = ROOT / "build" / "lambda"

FILES = (
    "main.py",
    "review_jobs.py",
    "review_worker.py",
    "dynamodb_usage.py",
    "lambda_handler.py",
    "requirements.txt",
)


def main():
    for name in FILES:
        source_file = SOURCE / name

        if source_file.is_symlink() or not source_file.is_file():
            raise RuntimeError(
                f"Expected a regular backend file: {name}"
            )

    for folder in (ROOT / "build", DESTINATION):
        if folder.is_symlink():
            raise RuntimeError(f"Build folder is a symlink: {folder}")

    DESTINATION.mkdir(parents=True, exist_ok=True)

    for existing in DESTINATION.iterdir():
        if (
            existing.name not in FILES
            or existing.is_symlink()
            or not existing.is_file()
        ):
            raise RuntimeError(
                f"Unexpected item in deployment folder: {existing.name}"
            )

    for name in FILES:
        shutil.copyfile(
            SOURCE / name,
            DESTINATION / name,
        )
        print(f"Copied: {name}")

    actual_files = {item.name for item in DESTINATION.iterdir()}
    assert actual_files == set(FILES)

    print()
    print("Deployment source folder prepared.")
    print(f"Location: {DESTINATION}")
    print("Verified: only the six listed files are present.")


if __name__ == "__main__":
    main()