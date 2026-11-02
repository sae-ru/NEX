"""Installed028 source-contract execution, source edits and genuine027 migration."""
from pathlib import Path
import hashlib,json,sys

SOURCE_CONTRACT_RESOURCE_PINS=(
 ('helper_sha256','tools/sdk_source_contracts.py'),
 ('test_source_sha256','tests/source_contract_cli.py'),
 ('origin_metadata_sha256','tests/fixtures/language-0.27-contract-origin.json'),
 ('origin_sql_sha256','tests/fixtures/language-0.27-contract-origin.sql'),
 ('guide_sha256','docs/source-contracts.md'),
 ('migration_guide_sha256','docs/source-contract-migration.md'),
)
def check_installed_source_contracts(cli,run,root,resources,compiler):
 from sdk_acceptance import require
 root,resources,compiler=Path(root),Path(resources),Path(compiler)
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 descriptor=cli('describe','--field','source_contracts')
 require(descriptor.get('language')=='0.28' and descriptor['value']['public_enabled'] is True,'SDK lacks ordinary028 contracts')
 output=root/'source-contracts028';test=resources/'tests/source_contract_cli.py'
 run([sys.executable,'-B',test,compiler,'--resources',resources,'--output',output],timeout=1800)
 file=output/'report.json';observed=json.loads(file.read_text())
 require(observed.get('ok') is True and observed.get('language')=='0.28' and observed.get('ordinary_CLI_only') is True and observed.get('compiler_sha256')==sha(compiler),'SDK contract test used another compiler')
 return {'schema':'nex.installed-source-contracts/1','ok':True,'language':'0.28','compiler_sha256':sha(compiler),
         **{key:sha(resources/path) for key,path in SOURCE_CONTRACT_RESOURCE_PINS},
         'execution_report_sha256':sha(file),'execution':observed,'migrated_revision':observed['migrated_revision']}
