# Epic Retrieval Agent Walkthrough

1. Run `service\run.ps1` with a generated API bearer secret and fixture backend.
   Show the red ASCII cross and listening API address.
2. Submit `source: files` for `DEMO-100042`. Watch the file search and completed
   job in the terminal. Download the synthetic XML ECG file using the result link.
3. Submit `source: ehr` and request JSON and FHIR output. In fixture mode this
   reads synthetic records, not a browser.
4. Run `service\tunnel.ps1` in a second shell after `devtunnel user login`.
   Make the same request through the authenticated HTTPS tunnel from another
   authorized client. The API also requires its own bearer token.
5. For a separately authorized training environment, launch `browser.ps1`, log in
   manually using a read-only account, and configure the exact Epic origin,
   Astra deployment, and `EPIC_BACKEND=computer-use`.
6. Restart the terminal service. Submit `source: ehr`; watch sanitized
   observe/click/scroll progress while Astra retrieves the existing chart.
7. Review patient/subject validation and source provenance in the result.
   Session expiry, unsafe actions, unavailable data, and model failures fail the
   job rather than returning fabricated data.
8. Stop the tunnel and API with Ctrl+C. Close the dedicated training browser.

Use synthetic data. Never tunnel the browser debugging port or bake browser
login state into a VM image. The repository does not ship a logged-in Epic session.
