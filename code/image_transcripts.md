# Image transcripts (PNG evidence)

Hand transcription of the 11 PNG files under `dataset/evidence/images/`, read by
viewing each image (no OCR). `code/ghost/parse_images.py` parses the tables below
into observations (`file_kind=image`, `captured_at` from `evidence_files.csv`).

Table columns, one row per evidence unit:

- `row`: on-screen row number, or the panel the value is in
- `role`: `OWN` = the unit's own resource; `REF:<owner>` = an id only mentioned
  by that unit (becomes a `REFERENCED` observation; `REF:` with no owner is never followed)
- `user_id` / `email` / `phone`: identifiers shown for that unit, verbatim (`—` = none shown)
- `state`: the parser vocabulary (PRESENT, IDENTIFIABLE, ACTIVE, ...); `category`: the record type

Names, order numbers, ticket numbers (CS-…), file names and timings are visible
but are not identifiers the linker uses. They are noted under "layout" only.

## evidence_04 — account_admin_console_20260926.png
Layout: Customer Operations customer page. Header "Haruka Sato · Silver", subline
`user_11 · account_5762`. Cards: Email, Phone, Signup channel mobile_app, Market JP. Orders
table (2 rows: ORD-20265762, ORD-20265518). Customer details panel: Support `CS-8538 · support_9538`.
Activity: "support_9538 created" (28 Aug).

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|
| header | account_service | account_5762 | OWN | user_11 | haruka.s1838@zoho.com | +81 90 7610 2507 | PRESENT | USER_PROFILE |
| details panel | support_platform | support_9538 | REF:account_5762 | — | — | — | REFERENCED | |

## evidence_09 — search_index_inspector_20260901.png
Layout: Search Console, query `email:g.silva76@gmail.com`, index customer_directory_v3 / prod-eu,
"2 hits". Results table: _id, Display name, Email, Customer reference, Score, Last indexed.
Raw document panel for search_428 repeats display_name / email / customer_reference.
Activity panel lists earlier queries: `customer_reference:user_9842` (1 hit), `display_name:"Aditi Jain"` (1 hit);
these are query strings, not results, and are not transcribed as units.

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|
| 1 | search_service | search_428 | OWN | user_13 | g.silva76@gmail.com | — | PRESENT | SEARCH_INDEX_ENTRY |
| 2 | search_service | search_1874 | OWN | — | g.silva76.jr@gmail.com | — | PRESENT | SEARCH_INDEX_ENTRY |

## evidence_14 — connector_management_console_20260807.png
Layout: BridgeOps Connections, "12 connectors", topology table: Connector, Destination,
Selector, Mode, Events/hour, Last contact. Rows 3-4 ("Order notifications", "Delivery tracking")
have no resource id and no identifier. Detail panel for data_flow_1121: Status Healthy,
Sync mode Continuous sync, Last response 200 OK.

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|
| 1 | integration_service | data_flow_1121 | OWN | — | jain.aditi@gmail.com | — | ACTIVE | DATA_FLOW |
| 2 | integration_service | data_flow_9846 | OWN | — | lucia-torres@gmail.com | — | ACTIVE | DATA_FLOW |

## evidence_19 — analytics_profile_view_20260713.png
Layout: Pulse Analytics user page. Header "Omar Darwish", subline
`user_20 · analytics_7438 · darwish.omar@icloud.com`. Event timeline (5 rows, products/values),
profile attributes (Market AE, Last activity 13 Jul 2026).

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|
| header | analytics_platform | analytics_7438 | OWN | user_20 | darwish.omar@icloud.com | — | IDENTIFIABLE | ANALYTICS_PROFILE |

## evidence_23 — customer_export_console_20260618.png
Layout: Customer Download Center, "4 jobs". Table: Export ID, Filename, Owner, Status, Created.
Detail panel for export_1260: Owner ingrid.dahl@outlook.com, Expires 25 Jun 2026, Download count 0,
Included Profile · Orders · Saved addresses.

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|
| 1 | export_service | export_1261 | OWN | — | marcus.lee@northstar.shop | — | PRESENT | USER_EXPORT |
| 2 | export_service | export_1260 | OWN | — | ingrid.dahl@outlook.com | — | PRESENT | USER_EXPORT |
| 3 | export_service | export_1259 | OWN | — | sara.kim@northstar.shop | — | PRESENT | USER_EXPORT |
| 4 | export_service | export_1258 | OWN | — | daniel.park@northstar.shop | — | PRESENT | USER_EXPORT |

Statuses as shown: 1 Collecting, 2 Ready, 3 Packaging, 4 Ready (all = the package exists).

## evidence_28 — support_ticket_console_20260524.png
Layout: Helpline Console ticket "CS-5034 · Where is my delivery?", subline
`support_1034 · Kofi Agyeman · Normal priority`. Cards: Customer, Email, Assigned Maya Chen.
Conversation table (4 messages, customer name as sender). Order ORD-20265034 panel.

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|
| header | support_platform | support_1034 | OWN | — | kagyeman8947@fastmail.com | — | IDENTIFIABLE | SUPPORT_MESSAGE |

## evidence_32 — backup_restore_console_20260429.png
Layout: Vault Recovery Manager, "Customer-platform archives", weekly snapshots. Table: Archive ID,
Account, Region, Created (all 26 Apr 02:00), Size, Encryption AES-256, Tier Archive.
Detail panel for backup_9287: Account areed1433@gmail.com, Retention end 26 Jul 2026.
Activity: "backup_9286 restored · Completed" (25 Apr), "backup_9281 restored · Completed" (24 Apr).
No restore-allowed / blocked flag is shown, so state is PRESENT (the archive exists), as the
text parsers do for an archive row without a restore decision.

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|
| 1 | backup_service | backup_9291 | OWN | — | bluepeakco@outlook.com | — | PRESENT | BACKUP_ARCHIVE |
| 2 | backup_service | backup_9288 | OWN | — | miller.logistics@company.com | — | PRESENT | BACKUP_ARCHIVE |
| 3 | backup_service | backup_9287 | OWN | — | areed1433@gmail.com | — | PRESENT | BACKUP_ARCHIVE |
| 4 | backup_service | backup_9286 | OWN | — | summit-retail@company.com | — | PRESENT | BACKUP_ARCHIVE |
| activity | backup_service | backup_9281 | REF: | — | — | — | REFERENCED | |

## evidence_37 — security_audit_explorer_20260905.png
Layout: Sentinel "Account events", subject filter `user_03 · 18-26 Aug 2026 UTC`, 6 signed events.
Table: Time, Event, Category, Subject, Actor, Integrity, Reference. Raw event panel for
audit_record_003 (account_closure_recorded, subject user_03). Ids are shown zero-padded.

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|
| 1 | security_service | audit_record_003 | OWN | user_03 | — | — | PRESENT | SECURITY_AUDIT_LOG |
| 2 | security_service | audit_record_002 | OWN | user_03 | — | — | PRESENT | SECURITY_AUDIT_LOG |
| 3 | security_service | audit_record_001 | OWN | user_03 | — | — | PRESENT | SECURITY_AUDIT_LOG |
| 4 | security_service | audit_record_006 | OWN | user_03 | — | — | PRESENT | SECURITY_AUDIT_LOG |
| 5 | security_service | audit_record_005 | OWN | user_03 | — | — | PRESENT | SECURITY_AUDIT_LOG |
| 6 | security_service | audit_record_004 | OWN | user_03 | — | — | PRESENT | SECURITY_AUDIT_LOG |

## evidence_42 — deleted_account_reference_20260310.png
Layout: Customer Reference Registry page titled `user_17`, badge "Retained reference",
Customer key · Account Platform · eu-west. Linked records: ORD-20263245, CS-3245, CS-3378,
FIN-7742 (all Active). No resource id (no `tombstone_*`), no email, no phone: no unit emitted.

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|

## evidence_46 — object_storage_browser_20260213.png
Layout: Nimbus Object Storage, bucket northstar-customer-data / support-attachments / 2026 / 02,
8 objects (delivery_confirmation_19.pdf, delivery_confirmation_20.pdf, return_label_4821.pdf,
return_label_4876.pdf, invoice_NS-10493.pdf, parcel_damage_7713.jpg,
customer_export_2026-02-10.zip, customer_export_2026-02-12.zip). No resource id, no user id,
email or phone: no unit emitted.

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|

## evidence_60 — marketing_profile_console.png
Layout: Audience Operations profile "Soo-jin Park · Live", subline
`marketing_001 · sj.park@naver.com · +82 10-5837-9451`. Cards: Market South Korea,
Email opt-in Yes, SMS opt-in No, Last refreshed 15 Sep 2026 23:40 UTC.

| row | system_id | resource_id | role | user_id | email | phone | state | category |
|---|---|---|---|---|---|---|---|---|
| header | marketing_platform | marketing_001 | OWN | — | sj.park@naver.com | +82 10-5837-9451 | PRESENT | MARKETING_PROFILE |

## Validation

Run `python3 code/ghost/parse_images.py` to re-check. Every user_id, email and phone was
looked up in `user_identities.csv` + `user_audit_log.csv`; every resource id was checked against
the resource-id prefix pattern. Values that fail are flagged as **suspected misread**, then
re-read from a zoomed crop of the image. Nothing is auto-corrected or snapped to a look-alike.

| file_id | value | check | resolution after zoomed re-read |
|---|---|---|---|
| evidence_09 | g.silva76.jr@gmail.com | email not in identities | confirmed as read; look-alike of a real email, kept verbatim (links nothing) |
| evidence_23 | marcus.lee@northstar.shop | email not in identities | confirmed as read; staff mailbox |
| evidence_23 | sara.kim@northstar.shop | email not in identities | confirmed as read; staff mailbox |
| evidence_23 | daniel.park@northstar.shop | email not in identities | confirmed as read; staff mailbox |
| evidence_32 | bluepeakco@outlook.com | email not in identities | confirmed as read; business account |
| evidence_32 | miller.logistics@company.com | email not in identities | confirmed as read; business account |
| evidence_32 | summit-retail@company.com | email not in identities | confirmed as read; business account |
| evidence_60 | sj.park@naver.com | email not in identities | confirmed as read; no identity has this email |
| evidence_60 | +82 10-5837-9451 | phone not in identities | confirmed as read; no identity has this phone |

`user_9842` (evidence_09 query history) is also not a known user, but it is a past query
string, not a transcribed unit. All 25 resource ids match the prefix pattern. Ids that occur only on
the screenshots (not in text evidence or activity): export_1258/1259/1261, backup_9281/9286/9288/9291,
audit_record_001/002/004/005/006 (zero-padded form).
