# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Added

- `src/leadgen/texts.py` — single source for user-facing strings. A reply used to
  live as a literal inside `message.answer(...)` and was duplicated in the e2e
  test and in the farm's `cases/*.yaml`; three copies of one phrase drift on the
  first edit. Handlers, `core/nav.py` and the e2e test now import the constants.
  `tests/test_texts_contract.py` guards it, including negative twins: a helper
  that drops its argument goes red.
- The repository presents itself as it is. The README became a front page — pitch,
  badges, a table of contents and user-facing sections — and issue forms plus a
  pull-request template now ask for the evidence this project acts on: what was
  run, what was expected, and how "done" would be able to fail.
- Governance layer brought to the family standard: `CONTRIBUTING.md`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md`, `AGENTS.md`, `.editorconfig`,
  `.gitattributes` and `CODEOWNERS`.
- `scripts/check-repo-contract.py` checks this repository against the shared
  contract, and `scripts/check-repo-contract_test.py` proves that checker can
  fail. A gate that has never gone red is an assumption, not a gate.

### Fixed

- `README-testing.md` was unreachable from the README in every bot of the family
  except one. A document nobody can reach is a document nobody reads; it is linked
  from the front page now.

### Changed

- Line endings are pinned to LF by `.gitattributes`, so a CRLF contributor no
  longer turns every touched line into a diff.

## [1.0.0] — 2026-10-13

Project running in production. See the git history for the work preceding this
entry; the changelog starts here because the repository had none.
