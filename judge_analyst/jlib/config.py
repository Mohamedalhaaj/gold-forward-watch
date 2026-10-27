"""The judge's pinned configuration.

A12_BUILD_COMMIT (§16.18 A12; R-AN-23, R-AN-67 A4): the gold-analyst main commit that builds A12. A call whose
`repo_head_sha` is that commit or has it as an ancestor must carry `analyst-context/3`, an earlier one
`analyst-context/2`; any other pairing is A4 `context_schema`. It is pinned at the build: None until the A12 build
commit is on gold-analyst main, and then every call is judged against `analyst-context/2`.

A14_BUILD_COMMIT (§16.18 A14; R-AN-23, R-AN-66, R-AN-67 A4 and A14): the gold-analyst main commit that builds A14. A
call whose `repo_head_sha` is that commit or descends from it must carry `analyst-context/4`; one that descends from
A12's build but not from A14's, `analyst-context/3`. It also anchors MODE.json `a14_from` (A14 `a14_from`). None until
the A14 build commit is on gold-analyst main: every call is then judged as before, and an `a14_from` that is set
gives the A0 WARNING `a14_unpinned`.
"""
A12_BUILD_COMMIT = "c45383a877848ee7616ac9d81efd51b7114f1a7e"   # gold-analyst A12 build (client approval 2026-10-26)
A14_BUILD_COMMIT = None                                        # gold-analyst A14 build: pinned once it is on main
