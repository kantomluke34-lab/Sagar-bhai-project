# Project implementation rule

Before calling a feature complete, trace its full user path: visible control, frontend payload, API validation, persistence, external integration, and the result shown back to the user. Verify that each control is reachable and that its downstream behavior matches the label. For WhatsApp features, check the Meta approval and sending paths separately. Report any path that cannot be verified with the available environment.
