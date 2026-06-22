# Resume

Drop your master résumé here — **PDF, LaTeX (`.tex`), Markdown (`.md`), or text
(`.txt`)**. Then in the **Profile** tab click **"Import from `resume/` folder"** and
Peregrine reads it into your profile (External parses it with the LLM; Internal hands
it to local Claude, then the panel polls for the result).

It uses `resume_path` from `config/profile.yml` if that's set and the file exists,
otherwise the **most recently modified** file in this folder. Importing records the
file as `resume_path` so re-imports reuse it. (Symlinks and `README.*` are ignored.)

Per-application tailored CVs are written under `applications/<id>/`. (This folder's
contents are gitignored — your résumé stays local.)
