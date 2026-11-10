# Publishing InterviewMirror AI safely

This folder is the **Submission Prep** build of InterviewMirror AI. It is a verified, offline-tested source snapshot, not the exact newer `app/main.py` revision shown in some earlier Windows screenshots. The current source contains compatibility endpoints for that older route family, but you should not replace the Windows checkout without comparing files.

## 1. Create an empty repository

Open <https://github.com/new> and create a repository called `interviewmirror-ai` under your GitHub account. Choose public only if you intend to publish all source code; private is safer while reviewing. **Do not** check "Initialize with README", `.gitignore`, or a license (this folder already has a README and `.gitignore`).

## 2. Run from this extracted folder

Open PowerShell, `cd` into this folder, and run:

```powershell
git --version
git init -b main
git add .
git status --short
```

Inspect the staged list. It must not include `.env`, personal recordings, API keys, or database files. Confirm that these commands show the key is ignored:

```powershell
git check-ignore .env
```

Do not proceed if you see secrets in `git status`.

## 3. Commit and push

```powershell
git commit -m "Initial InterviewMirror AI submission prep build"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/interviewmirror-ai.git
git push -u origin main
```

Replace `YOUR_GITHUB_USERNAME` with your actual account login. GitHub may ask you to authenticate in the browser. Do not paste an access token into chat.

If a repository already exists and contains changes, do **not** force-push: clone that repository first, compare its files, and merge intentionally.

## 4. Confirm on GitHub

Verify `README.md`, `.env.example`, `main.py`, `gnani.py`, `evaluation.py`, `static/`, and `tests/` are visible. The GitHub Actions workflow will run the offline tests on new pushes.

## Run locally

```powershell
powershell -ExecutionPolicy Bypass -File .\QUICKSTART_WINDOWS.ps1
```

Then browse to <http://127.0.0.1:8001>. Add credentials only to your local `.env` file, never to the repository.
