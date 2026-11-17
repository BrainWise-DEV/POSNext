# FF Phase 2 test baseline (before Phase 2 changes)

Branch `feature/ff-phase2-unlock`, site nexus.local, run via
`bench --site nexus.local execute pos_next.dev_tests.run --kwargs '{"module": "<module>"}'`.

| Module | Run | Result |
|---|---|---|
| pos_next.api.test_email_verification | 41 | OK |
| pos_next.api.test_customers | 14 | 1 failure (pre-existing): `test_get_default_loyalty_program_from_settings_uses_explicit_pos_profile` |
| pos_next.test_no_promotions_import | 9 | OK |
| pos_next.test_split_smoke | 13 | OK |
| `yarn test:run src/components/sale/__tests__ src/utils/__tests__` | 200 tests / 26 files | all passed |

The one backend failure is pre-existing and was not fixed.
