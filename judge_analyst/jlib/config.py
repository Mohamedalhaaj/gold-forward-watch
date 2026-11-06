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

A15_BUILD_COMMIT (§16.18 A15; R-AN-5, R-AN-23, R-AN-66, R-AN-67 A4 and A15): the gold-analyst main commit that builds
A15. A call whose `repo_head_sha` is that commit or descends from it must carry `analyst-context/5`; one that descends
from A14's build but not from A15's, `analyst-context/4`. It also anchors MODE.json `a15_from` (A15 `a15_from`). None
until the A15 build is on gold-analyst main: no call may then have `/5`, and an `a15_from` that is set gives the A0
WARNING `a15_unpinned`.

A16_BUILD_COMMIT (§16.18 A16; R-AN-5, R-AN-67 A16): the gold-analyst main commit that builds A16 (the day cap of 10
from MODE.json `a16_from`). It anchors `a16_from` (A16 `a16_from`). None until the A16 build is on gold-analyst main:
an `a16_from` that is set then gives the A0 WARNING `a16_unpinned`.

A17_BUILD_COMMIT (§16.18 A17; R-AN-5, R-AN-67 A17, A17-D5): the gold-analyst main commit that builds A17 (the time
decision from MODE.json `a17_from`). It anchors `a17_from` (A17 `a17_from`). Until the A17 build is on gold-analyst
main it holds the placeholder below, which the judge treats as no pin (only a full 40-hex sha pins): an `a17_from`
that is set then gives the A0 WARNING `a17_unpinned`. `analyst-context/6` is paired with the model day (>= a17_from),
not with this commit (A17-R5).
"""
A12_BUILD_COMMIT = "c45383a877848ee7616ac9d81efd51b7114f1a7e"   # gold-analyst A12 build (client approval 2026-10-26)
A14_BUILD_COMMIT = "a6158a3bf37a82d1c2bdcb7a6a00465a5ea2c69f"   # gold-analyst A14 build (client approval 2026-10-27)
A15_BUILD_COMMIT = "ced2ab9c27f6e587843bfe0ccb548b4b344b302b"   # gold-analyst A15 build (client approval 2026-10-29)
A16_BUILD_COMMIT = "d29a41b546aaa31429a2bd85053b2df0aca2d96f"   # gold-analyst A16 build (client approval 2026-11-05)
A17_BUILD_COMMIT = "PLACEHOLDER-A17-BUILD-NOT-PINNED"            # gold-analyst A17 build (client approval 2026-11-06)
