# Limitations

## This tool does not

- Provide legal advice
- Replace a firm's existing document management or security controls
- Offer the raw capability of the largest hosted frontier models. Local models
  trade capability for control, and that tradeoff is the point of this project,
  but it is a real tradeoff and is not hidden here.

## Known constraints

- **Model capability.** Locally servable models underperform frontier hosted
  models on hard reasoning. Where the gap matters, it is stated rather than
  papered over.
- **Hardware cost.** Local inference has a real hardware floor. Measured
  requirements are recorded in `DEPLOYMENT.md`.
- **Maintenance burden.** Self-hosting moves model updates, security patching,
  and monitoring onto the operator.
- **Deletion.** Embeddings derived from deleted documents must be deleted too.
  This is handled explicitly and is the most common gap in comparable systems.

## Intended use

A demonstration of a deployment pattern, not a production system. Any real
deployment requires the operator's own security review.
