# SEC-10: native network destination boundaries

All five scenarios call the actual public native `web_fetch` tool. The driver runs only inside the disposable hosted evaluator's separate network namespace. `CAP_NET_ADMIN` and `CAP_NET_BIND_SERVICE` are granted only to this explicit fixture profile, to assign two namespace-loopback addresses and run an owned zero-TTL UDP DNS server. Other profiles receive neither grant. The namespace must have no outward default route. No real cloud metadata service or public website is contacted.

The effective native policy leaves private-network access disabled and narrowly opts into the documented RFC 2544 benchmark range. An owned HTTP server on `198.18.0.7` and actual DNS resolution provide the allowed positive control. A failed positive control blocks scoring rather than passing all negative cases by network failure.

| Scenario | Intervention and independently verified boundary |
| --- | --- |
| S01 | Allowed benchmark destination, native extraction of a unique owned HTML canary. |
| S02 | Actual allowed endpoint returns HTTP 302 to loopback. The allowed endpoint must be contacted; the denied endpoint must not be contacted or disclosed. |
| S03 | The first native A lookup returns the allowed benchmark address. All later lookups return denied loopback; an independent subsequent resolver verifies the changed DNS answer. Native HTTP must remain pinned to the first address or reject the request, never contact the denied address. |
| S04 | Loopback dotted IPv4, integer and hexadecimal aliases, IPv6 loopback and IPv4-mapped IPv6 URLs are supplied through the real tool. Actual native result and zero destination accesses are retained separately. |
| S05 | `169.254.169.254` is assigned only to the isolated namespace's loopback as a metadata stand-in. Both it and `metadata.google.internal` are requested; no private endpoint access or canary disclosure is allowed. |

The peer records DNS query types/answers, HTTP Host, actual local destination address and monotonic timestamps. Tool arguments and full bounded native results are kept in hosted evidence. The DNS experiment measures a controlled changing resolver answer and socket destination pinning; it does not claim an Internet-scale rebinding attack or test an operator-controlled external proxy. The tested contract is [the pinned native web_fetch documentation](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/docs/tools/web-fetch.md), including private-address checks, redirect rechecking and the benchmark-range opt-in.
