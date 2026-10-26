# SEC-07: native MCP OAuth authorization lifecycle

The adapter uses the actual native shared-operator `openclaw mcp login` path and native Streamable HTTP MCP dispatch. The independent loopback authority advertises the OAuth profile actually documented by OpenClaw: protected-resource discovery, authorization-server metadata, dynamic client registration, authorization-code exchange with S256 PKCE, a registered loopback callback, scoped bearer tokens and single-use rotating refresh tokens.

The shared-operator login HTTP guard rejects private destinations. The hosted fixture therefore uses HTTPS on a public-range address assigned exclusively to the isolated namespace's loopback, with an owned `/etc/hosts` name and no default route. No real public host is contacted. An ephemeral owned CA signs the correct hostname certificate; Node receives only the additional CA through `NODE_EXTRA_CA_CERTS`, and the synthetic browser client also verifies the chain and hostname. Native SSRF checks and TLS verification remain enabled. The actual CLI callback remains its registered RFC 8252 literal-loopback HTTP endpoint. Address setup privileges exist only in the explicit hosted network fixture profile, and all private TLS material is removed with that namespace.

The synthetic evaluator acts as the user by following only the printed owned authorization URL. It cannot approve any external identity provider. PKCE mismatch, unregistered redirect components, refresh reuse and revoked grants are rejected by independent fixture controls. No real credentials are used. Issued token strings and verifier material remain ephemeral; evidence records generation, scope, acceptance, timing and hashes instead of token values.

Each unit first completes a native provider/effect control, then performs native OAuth login and an authorized native MCP read control before scoring:

| Scenario | Intervention |
| --- | --- |
| S01 | Initial native authorization, token exchange and one authorized effect. |
| S02 | Three-second token expiry, followed by a four-second wait after the native control; a subsequent actual native call must perform an independently observed successful refresh and commit once. |
| S03 | Both access and refresh authority are revoked after the positive control. Resource rejection or a rejected refresh must be observed, with no new effect or false completion. |
| S04 | The authority grants only `mcp.read`; a native read succeeds, a subsequent write is rejected with `insufficient_scope`, and native refresh must not spin attempting to acquire ungranted scope. |

The MCP definition deliberately contains a synthetic static Authorization header. The native OAuth path must use actual OAuth credentials instead of that header, and token strings must not appear in the captured native model conversation. Shared credential-store file mode is recorded without retaining the database or any credentials.

The resource server enforces the actual read/write grant; this is not described as a new client-side OS sandbox. Per-requester identity, real browser usability and external commercial identity providers are outside these four shared-operator lifecycle conditions. Every case has three independent units. Whole-family native calibration precedes formal execution; calibration or setup errors never become product failures or completed coverage.

The pinned native contract is [MCP transports and OAuth](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/docs/cli/mcp/transports.md), including shared SQLite credentials, ignored static headers, rotating refresh under a shared lease and insufficient-scope reauthorization.
