# Export exclusions and limitations

The original server inventory found 2,778 candidate text files across source, third-party code and configuration, with 46 files flagged by its first hardcoded-secret scan. The import used a stricter scope and additional content checks; 782 ABUTRON-relevant files were committed.

- Entire or partial excluded categories: `.env`, private credentials/certificates, database rows and dumps, MT5 terminal profiles, session/cookie data, logs, images/screenshots containing account details, build caches, virtualenvs, third-party AgenticTrading and TradingAgents source trees, MetaQuotes standard Include/Indicators/Scripts and example MQL5 sources, compiled binaries and backups.
- Some security-sensitive source paths were rejected on pattern matches; a pattern match does not prove the file contained an actual credential.
- The selected candidate inventory included 12 paths not published: ten vendor example MQL5 sources and two option-C native probe scripts; these require separate review, not silent inclusion.
- The binary PDF/DOCX documentation in ChatGPT was not transferred by the GitHub connector. The repository is NOT a complete disaster recovery image or a production certification.
- Historical old research, SMC/ICT and other retired code may be present in the source snapshot for provenance. It is not an instruction to enable it.

Never publish this snapshot publicly. Before deploying any of this code, validate exact running service versions, broker accounts, customer authorization, protective stop behavior, rollback and license entitlements.
