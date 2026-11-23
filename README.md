# STUDY//SCOUT

A terminal app for clinical-trials business development at a research site.
It searches [ClinicalTrials.gov](https://clinicaltrials.gov) for studies that
fit your site and groups them into one dossier per sponsor: their trials,
their contacts, your pipeline history and your notes. It also tracks the
pipeline, study start-up paperwork, off-registry leads and follow-up dates.
An optional LLM assistant drafts outreach emails; everything else works
without it.

![The sponsor dossier](docs/dossier.png)

## Install

Linux, Python 3.11 or newer.

```bash
git clone https://github.com/serize-dev/studyscout.git
cd studyscout
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/studyscout
```

Fedora: build a self-contained RPM instead (it bundles its own Python).

```bash
bash packaging/build_rpm.sh
sudo dnf install ./dist/rpm/RPMS/x86_64/studyscout-*.rpm
```

The first run creates `~/.config/studyscout/profile.toml` and `site.md`.
Describe your site in `site.md`, press `f` to set your search, then `r` to
run it. To turn on the assistant, add an Anthropic API key under
`CONNECTIONS` or set `ANTHROPIC_API_KEY`.

Full manual: [HANDBOOK.md](HANDBOOK.md). MIT licensed. Not affiliated with
ClinicalTrials.gov or the NLM.
