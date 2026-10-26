"""The judge's pinned configuration.

A12_BUILD_COMMIT (§16.18 A12; R-AN-23, R-AN-67 A4): the gold-analyst main commit that builds A12. A call whose
`repo_head_sha` is that commit or has it as an ancestor must carry `analyst-context/3`, an earlier one
`analyst-context/2`; any other pairing is A4 `context_schema`. It is pinned at the build: None until the A12 build
commit is on gold-analyst main, and then every call is judged against `analyst-context/2`.
"""
A12_BUILD_COMMIT = "c45383a877848ee7616ac9d81efd51b7114f1a7e"   # gold-analyst A12 build (client approval 2026-10-26)
