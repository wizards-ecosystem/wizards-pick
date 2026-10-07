# Storage and output decisions

The September 6 BhavAI and Papercut reviews were rechecked on October 7.
Implemented from scratch: bounded head/tail excerpts in model context, console and
reports; three-request completion continuation retaining the output cap; transactional,
versioned SQLite migrations with legacy-data retention and future-version refusal.
The command capture limit still terminates runaway output; it is not a rolling log.

Declined: automatic cross-session finding merging. Pick has no engagement identity
or reliable per-finding target coordinate. Normalized titles can merge distinct
vulnerabilities and discard differing evidence. Findings remain separate observations
inside their original sessions, and report counts retain that meaning.

Declined: rejecting data directories inside Git trees. The current documented default
is the ignored project-local `.wizards-pick/` directory. Owner-only file permissions
remain enforced. A blanket refusal contradicts that supported installation model.

Historical sources: BhavAI Terminal Edition at
`67e329da154afc0722c080ae6af9b79e2fdf3b94` (no code reuse permitted), and Papercut at
`b9570df` (MIT). Only techniques were independently implemented; no upstream code
was copied or run. This record closes the two temporary review handoffs without
claiming that declined proposals were implemented.
