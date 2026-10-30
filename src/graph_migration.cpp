#include "nex/migration.h"
#include "nex/project.h"
#include "nex/task_frontend.h"

namespace nex {
GraphMigrationPlan preflightGraphMigration(const std::filesystem::path &directory,
    const std::string &originRevision,const std::string &expectedHead,
    SourceLanguage target,const llvm::json::Object *reviewedCandidate){
  if(expectedHead.empty())throw Error("E_OPTION","graph migration requires a nonempty expected HEAD");
  Program version;version.sourceLanguage=target;const auto language=programLanguage(version);
  std::error_code error;const auto physical=std::filesystem::canonical(directory,error);
  if(error)throw Error("E_STORE","graph migration requires an existing source store");
  // ReadOnly cannot create the destination or upgrade its schema. Rechecking
  // the origin under its retained parser precedes any candidate acceptance.
  Store archive(physical,StoreOpenMode::ReadOnly);
  const auto previous=archive.headRevision();
  if(previous!=(expectedHead=="EMPTY"?"":expectedHead))throw Error("E_CONFLICT","graph HEAD changed before migration preflight");
  const auto original=originRevision=="HEAD"?previous:originRevision;
  const auto originLanguage=archive.revisionLanguage(original);
  auto sources=archive.bundle(original);
  const bool verified=verifyMigrationOrigin(sources,physical.parent_path(),originLanguage,original,target);
  const auto originHash=hash(json(sources,false));
  if(reviewedCandidate){
    const auto &candidate=*reviewedCandidate;
    if(candidate.size()!=6||candidate.getString("schema")!="nex.migration-candidate/1"||
       candidate.getString("origin_revision")!=original||candidate.getString("origin_language")!=originLanguage||
       candidate.getString("origin_source_hash")!=originHash||candidate.getString("target_language")!=language||!candidate.getObject("sources"))
      throw Error("E_MIGRATION_CANDIDATE","reviewed candidate origin/source/target guards differ");
    sources=llvm::json::Object(*candidate.getObject("sources"));
  }
  auto checked=preflightMigrationTarget(sources,physical.parent_path(),target);
  const auto targetRevision=revision(checked);
  auto snapshot=sourceBundle(checked);
  if(revision(loadVersionedBundle(snapshot,physical.parent_path().string(),language))!=targetRevision)
    throw Error("E_REVISION","migration candidate failed its versioned archive roundtrip");
  GraphMigrationPlan result;
  result.directory=physical;result.identityNamespace=archive.identityNamespace();result.target=target;result.originRevision=original;result.originLanguage=originLanguage;
  result.originSourceHash=originHash;result.expectedHead=expectedHead;result.targetRevision=targetRevision;
  result.targetSourceHash=hash(json(snapshot,false));result.sources=std::move(snapshot);
  result.originVerified=verified;result.candidateUsed=reviewedCandidate!=nullptr;return result;
}
llvm::json::Object applyGraphMigration(const GraphMigrationPlan &plan,const ChangeInfo &change){
  if(change.action!="migrate")throw Error("E_OPTION","graph migration requires an explicit migrate change action");
  validateChangeInfo(change);
  Program version;version.sourceLanguage=plan.target;const auto language=programLanguage(version);
  const llvm::json::Object candidate{{"schema","nex.migration-candidate/1"},{"origin_revision",plan.originRevision},
    {"origin_language",plan.originLanguage},{"origin_source_hash",plan.originSourceHash},
    {"target_language",language},{"sources",plan.sources}};
  // A cached plan grants no write authority: recheck both the retained origin
  // and current HEAD before opening writable state, including on retries.
  auto current=preflightGraphMigration(plan.directory,plan.originRevision,plan.expectedHead,plan.target,&candidate);
  if(current.identityNamespace!=plan.identityNamespace)throw Error("E_CONFLICT","migration graph identity namespace changed");
  if(current.targetRevision!=plan.targetRevision||current.targetSourceHash!=plan.targetSourceHash||current.originVerified!=plan.originVerified)
    throw Error("E_REVISION","migration plan differs from its checked target or retained origin");
  auto program=loadVersionedBundle(current.sources,plan.directory.parent_path().string(),language);
  Store destination(plan.directory);
  // Store::save repeats the expected-HEAD guard inside its write transaction.
  const auto saved=destination.save(program,plan.expectedHead,true,change,plan.identityNamespace);
  return llvm::json::Object{{"schema","nex.graph-migration/1"},{"ok",true},
    {"origin_revision",current.originRevision},{"origin_language",current.originLanguage},
    {"origin_verified",current.originVerified},{"origin_source_hash",current.originSourceHash},
    {"revision",saved},{"language",language},{"source_hash",current.targetSourceHash},{"identity_namespace",plan.identityNamespace},
    {"changed",plan.expectedHead!=saved},{"candidate_used",plan.candidateUsed},{"materialized",false}};
}
}
