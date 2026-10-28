#include "nex/task_provider_debug.h"
#include "nex/task_ir.h"
#include "nex/task_frontend.h"
#include "nex/incremental.h"
#include "nex/operations.h"
#include "nex/native_images.h"
#include "nex_task_debug.h"
#include "nex_json.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/SHA256.h"
#include "llvm/ADT/StringExtras.h"
#include <algorithm>
#include <filesystem>
#include <functional>

namespace nex {
namespace {
namespace fs=std::filesystem;
using Object=llvm::json::Object;using Array=llvm::json::Array;using JSON=llvm::json::Value;
[[noreturn]] void fail(const std::string &message){throw Error("E_TASK_DEBUG",message);}
std::string text(const Object &o,const char *key){auto p=o.getString(key);if(!p||p->empty()||p->contains('\0'))fail(std::string("missing debug field: ")+key);return p->str();}
JSON parse(const std::string &raw){try{nexrt::validateJSONText(raw);}catch(const nexrt::DataError &e){fail(e.what());}auto v=llvm::json::parse(raw);if(!v)fail("invalid debug JSON: "+llvm::toString(v.takeError()));return std::move(*v);}
std::string sha(const std::string &raw){return llvm::toHex(llvm::SHA256::hash(llvm::arrayRefFromStringRef(raw)),true);}
fs::path closed(const fs::path &root,const std::string &relative){
  fs::path name(relative);if(name.empty()||name.is_absolute()||name.lexically_normal()!=name)fail("invalid debug relative input");
  for(const auto &part:name)if(part==".."||part=="."||part.empty())fail("escaping debug relative input");
  auto base=fs::absolute(root).lexically_normal();fs::path current;
  for(const auto &part:base){current/=part;if(fs::is_symlink(current))fail("symlink debug artifact directory");}
  for(const auto &part:name){current/=part;if(fs::is_symlink(current))fail("symlink debug completed input");}
  return base/name;
}
std::string read(const fs::path &root,const std::string &name,uint64_t limit=64*1048576){auto p=closed(root,name);if(!fs::is_regular_file(p)||fs::file_size(p)>limit)fail("missing/oversized completed debug input: "+name);return readFile(p.string());}
void put(const fs::path &root,const std::string &name,const std::string &bytes){auto p=closed(root,name);if(fs::is_regular_file(p)&&readFile(p.string())==bytes)return;writeFile(p.string(),bytes);}
const NativeTaskDebugSourceComponent &component(const NativeTaskDebugSourceUnion &sources,const std::string &name){for(const auto &entry:sources.components)if(entry.component==name)return entry;fail("debug registry has no checked source component");}
std::string unitSource(const Program &p,const Function &function){auto unit=p.units.find(function.unit);return unit==p.units.end()?p.source:unit->second.source;}
std::string module(const Program &p,const Function &function){auto unit=p.units.find(function.unit);return unit==p.units.end()?p.module:unit->second.module;}
void image(const Object &row,bool runtime){
  if(row.size()!=7||!row.get("component")||(!row.get("component")->getAsNull()&&!row.getString("component")))fail("invalid debug image row");
  for(auto key:{"path","key","hash","sha256","uuid","kind"})text(row,key);
  if(fs::path(text(row,"path")).is_absolute()==false||fs::path(text(row,"path")).lexically_normal()!=fs::path(text(row,"path")))fail("invalid debug image path");
  if(runtime){if(row.getString("kind")!="application"&&row.getString("kind")!="runtime")fail("invalid catalog runtime image kind");}
  else if(!row.getString("component")||(row.getString("kind")!="application"&&row.getString("kind")!="shared-image"))fail("invalid debug code-owner image kind");
}
void physicalImage(const Object &row,bool runtime){image(row,runtime);auto path=fs::path(text(row,"path"));auto bytes=read(path.parent_path(),path.filename().string(),512*1048576);if(hash(bytes)!=text(row,"hash")||sha(bytes)!=text(row,"sha256")||nativeImageUUID(path.string())!=text(row,"uuid"))fail("physical debug image bytes/UUID differ");}
}

std::string nativeTaskDebugMetadataHash(const NativeTaskDebugCatalog &catalog,const NativeTaskDebugSourceUnion &sources){auto info=nativeTaskDebugInfo(catalog,sources);return hash(json(Object{{"schema","nex.task-debug-metadata/2"},{"catalog_hash",info.catalogHash},{"source_union_hash",info.sourceUnionHash}},false));}

NativeTaskDebugCheckedSources validateNativeTaskDebugSources(const NativeTaskDebugCatalog &catalog,
    const NativeTaskDebugSourceUnion &sources,const std::map<std::string,std::string> &bundles){
  (void)nativeTaskDebugInfo(catalog,sources);
  if(sources.components.size()>128||bundles.size()!=sources.components.size())fail("debug source component count differs");
  NativeTaskDebugCheckedSources checked;size_t total=0;std::set<std::string> all;
  for(const auto &source:sources.components){
    auto raw=bundles.find(source.component);if(raw==bundles.end()||raw->second.size()>16*1048576||raw->second.size()>64*1048576-total)fail("debug source bundle bound/missing input");total+=raw->second.size();
    if(source.bundleFile!="debugger/components/"+source.component+"/source-bundle.json"||hash(raw->second)!=source.bundleHash)fail("debug source bundle pin/path differs");
    auto value=parse(raw->second);if(hash(json(value,false))!=source.sourceHash)fail("debug component semantic source hash differs");
    auto p=loadVersionedBundle(value,"<task-debug:"+source.component+">",source.language);
    if(programLanguage(p)!=source.language||revision(p)!=source.revision)fail("debug component language/revision differs");
    p.function(source.entry);bool retainedStage=isPublicTaskLanguage(p)&&usesTaskEffects(p,source.entry);for(const auto &name:source.exports){if(!p.function(name).exported)fail("debug source export is not public");retainedStage|=isPublicTaskLanguage(p)&&usesTaskEffects(p,name);}
    std::map<std::string,std::string> contracts;for(const auto &unit:planNative(p,source.entry,source.exports,true).units){auto value=parse(unit.contract);auto o=value.getAsObject();if(!o)fail("invalid checked debug native contract");o->erase("unit");contracts.emplace(unit.identity,hash(json(Object(*o),false)));}
    std::map<std::string,const NativeTaskDebugCode*> codes;for(const auto &registry:catalog.registries)if(registry.component==source.component)for(const auto &code:registry.codes)codes.emplace(code.name,&code);
    for(const auto &entry:source.definitions){
      if(!all.insert(entry.name).second)fail("duplicate physical debug definition");const auto &fn=p.function(entry.name);auto content=unitSource(p,fn);
      auto anchor=hash(json(Array{"nex.native-source-anchor/2",module(p,fn)},false));auto path=fs::path(entry.debugPath);
      if(entry.functionHash!=hash(json(canonical(fn),false))||entry.functionSourceHash!=hash(p.definition(fn))||entry.sourceUnitHash!=hash(content)||entry.line!=int64_t(fn.span.line)||!contracts.contains(entry.name)||entry.contract!=contracts.at(entry.name)||
         !path.is_absolute()||path.lexically_normal()!=path||path.filename()!="source.nex"||path.parent_path().filename()!=anchor||path.parent_path().parent_path().filename()!="source-anchors"||entry.retained!=retainedStage||entry.retained!=codes.contains(entry.name))fail("debug owned definition differs from checked component source: "+entry.name);
      if(auto code=codes.find(entry.name);code!=codes.end()){
        auto expected=taskDebugFunctionMetadata(p,fn,entry.debugPath);
        if(code->second->functionHash!=entry.functionHash||code->second->functionSourceHash!=entry.functionSourceHash||code->second->sourceUnitHash!=entry.sourceUnitHash||code->second->debugPath!=entry.debugPath||code->second->contract!=entry.contract||json(Object(code->second->metadata),false)!=json(std::move(expected),false))fail("debug point/binding metadata differs from checked component source: "+entry.name);
      }
    }
    checked.emplace(source.component,std::move(p));
  }
  for(const auto &source:sources.components){auto plan=planNative(checked.at(source.component),source.entry,source.exports,true);std::set<std::string> reachable;
    for(const auto &unit:plan.units){reachable.insert(unit.identity);if(catalog.artifact==NativeTaskArtifactKind::Application&&!all.contains(unit.identity))fail("debug source union omits a checked physical definition: "+unit.identity);}
    for(const auto &entry:source.definitions)if(!reachable.contains(entry.name))fail("debug source union claims an unselected physical definition: "+entry.name);
  }
  return checked;
}

NativeTaskDebugCheckedSources loadNativeTaskDebugSources(const std::string &directory,const NativeTaskDebugCatalog &catalog,const NativeTaskDebugSourceUnion &sources){std::map<std::string,std::string> bundles;for(const auto &source:sources.components)if(!bundles.emplace(source.component,read(directory,source.bundleFile,16*1048576)).second)fail("duplicate debug source component");return validateNativeTaskDebugSources(catalog,sources,bundles);}

Array nativeTaskDebugSourceInputs(const NativeTaskDebugCatalog &catalog,const NativeTaskDebugSourceUnion &sources,const std::map<std::string,std::string> &bundles){auto checked=validateNativeTaskDebugSources(catalog,sources,bundles);Array result;std::set<std::string> projections;for(const auto &source:sources.components){result.push_back(Object{{"kind","debug_source_bundle"},{"path",source.bundleFile}});const auto &p=checked.at(source.component);for(const auto &entry:source.definitions)projections.insert("debugger/source-cache/"+hash(unitSource(p,p.function(entry.name)))+"/source.nex");}if(projections.size()>8192)fail("debug source projection count exceeds bound");for(const auto &path:projections)result.push_back(Object{{"kind","debug_source_projection"},{"path",path}});return result;}

Array writeNativeTaskDebugSources(const std::string &directory,const NativeTaskDebugCatalog &catalog,
    const NativeTaskDebugSourceUnion &sources,const std::map<std::string,std::string> &bundles){
  auto checked=validateNativeTaskDebugSources(catalog,sources,bundles);std::map<std::string,std::string> mappings;
  for(const auto &source:sources.components){put(directory,source.bundleFile,bundles.at(source.component));const auto &p=checked.at(source.component);
    for(const auto &entry:source.definitions){const auto &fn=p.function(entry.name);auto contents=unitSource(p,fn);auto relative="debugger/source-cache/"+hash(contents)+"/source.nex";put(directory,relative,contents);
      auto from=fs::path(entry.debugPath).parent_path().string(),to=closed(directory,relative).parent_path().string();auto [old,inserted]=mappings.emplace(from,to);if(!inserted&&old->second!=to)fail("conflicting immutable debug source anchor");}
  }
  Array result;for(const auto &[from,to]:mappings)result.push_back(Array{from,to});return result;
}

Object finalizeNativeTaskDebugManifest(Object base,const NativeTaskDebugCatalog &catalog,
    const NativeTaskDebugSourceUnion &sources,const std::map<std::string,std::string> &bundles,
    Array codeImages,Object runtimeImage){
  auto checked=validateNativeTaskDebugSources(catalog,sources,bundles);auto info=nativeTaskDebugInfo(catalog,sources);
  if(catalog.artifact!=NativeTaskArtifactKind::Application||catalog.ownerImage.empty()||codeImages.empty()||codeImages.size()>128)fail("provider debug launch requires its actual application closure");
  std::map<std::string,const Object*> owners;for(const auto &value:codeImages){auto row=value.getAsObject();if(!row)fail("invalid debug owner");image(*row,false);if(!owners.emplace(text(*row,"component"),row).second)fail("duplicate debug image component");}
  if(!owners.contains(catalog.ownerImage)||owners.at(catalog.ownerImage)->getString("kind")!="application")fail("debug root image association differs");image(runtimeImage,true);
  if((catalog.mode==NativeTaskLinkageMode::Static&&(owners.size()!=1||json(Object(runtimeImage),false)!=json(Object(*owners.at(catalog.ownerImage)),false)))||
     (catalog.mode==NativeTaskLinkageMode::SharedFixed&&(runtimeImage.getString("kind")!="runtime"||!runtimeImage.get("component")->getAsNull())))fail("debug runtime owner differs from linkage mode");
  Array functions,registries;int64_t index=0,registryIndex=0;std::set<std::string> heap;
  if(auto original=base.getArray("heap_types"))for(const auto &value:*original)if(auto name=value.getAsString())heap.insert(name->str());
  for(const auto &registry:catalog.registries){if(!owners.contains(registry.ownerImage))fail("debug registry has no physical code owner");const auto &source=component(sources,registry.component);const auto &p=checked.at(source.component);
    registries.push_back(Object{{"component",registry.component},{"accessor",registry.accessor},{"owner_image",registry.ownerImage},{"first_code",index},{"code_count",int64_t(registry.codes.size())}});
    std::map<std::string,std::pair<const NativeTaskDebugCode*,int64_t>> codes;int64_t local=0;for(const auto &code:registry.codes)codes.emplace(code.name,std::pair{&code,++local});
    std::set<std::string> definitions;for(const auto &entry:source.definitions)definitions.insert(entry.name);auto bridges=nativeFunctionBridges(p,definitions);
    std::function<void(const Type&)> type=[&](const Type &t){if(!t.heap()||!heap.insert(typeName(t)).second)return;if(t.element)type(*t.element);for(const auto &arg:t.arguments)type(arg);if(t.kind==Type::Record)for(auto member:p.structure(t.name).members())type(member->type);};
    for(const auto &entry:source.definitions){const auto &fn=p.function(entry.name);type(fn.result);for(const auto &param:fn.params)type(param.type);for(const auto &capture:fn.captures)type(capture.type);
      std::function<void(const std::vector<S>&)> locals=[&](const auto &body){for(const auto &s:body){type(s->type);childBlocks(s,locals);}};locals(fn.body);
      Object function{{"name",entry.name},{"component",source.component},{"owner_image",source.ownerImage},{"language",source.language},{"source_revision",source.revision},{"source_hash",source.sourceHash},{"source_unit_hash",entry.sourceUnitHash},{"contract",entry.contract},{"node_id",nullptr},
        {"function_hash",entry.functionHash},{"function_source_hash",entry.functionSourceHash},{"native_symbol",nativeSymbol(entry.name)+(entry.retained?"__task_step":"")},{"callable_symbol",fn.effects.contains("task")?"":fn.closure?nativeSymbol(entry.name):bridges.contains(entry.name)?nativeSymbol(entry.name)+"__closure_bridge":""},
        {"task_continuation_symbol",entry.retained?nativeSymbol(entry.name)+"__task_step":""},{"operation_sites",operationSites(fn,operationTree(p,fn))},{"task_debug",nullptr}};
      if(auto code=codes.find(entry.name);code!=codes.end()){auto metadata=Object(code->second.first->metadata);metadata["site_id"]=index+code->second.second;function["task_debug"]=std::move(metadata);function["registry_index"]=registryIndex;function["local_site_id"]=code->second.second;}
      functions.push_back(std::move(function));
    }
    index+=registry.codes.size();++registryIndex;
  }
  if(!index||index>16384)fail("debug root logical code count is outside bounds");
  std::map<std::string,Object> sourceRows;auto folder=base.getString("artifact_directory")?fs::path(text(base,"artifact_directory")):fs::path(text(base,"program")).parent_path();base["artifact_directory"]=folder.string();
  for(const auto &source:sources.components){const auto &p=checked.at(source.component);for(const auto &entry:source.definitions){const auto &fn=p.function(entry.name);auto contents=unitSource(p,fn);auto projection=closed(folder,"debugger/source-cache/"+hash(contents)+"/source.nex");
    Object row{{"original",fn.unit},{"projection",projection.string()},{"debug_path",entry.debugPath},{"hash",hash(contents)}};auto [old,inserted]=sourceRows.emplace(entry.debugPath,std::move(row));if(!inserted&&(old->second.getString("hash")!=hash(contents)||old->second.getString("projection")!=projection.string()))fail("conflicting debug source projection");
  }}
  Array maps,projected;for(const auto &[anchor,row]:sourceRows){maps.push_back(Array{fs::path(anchor).parent_path().string(),fs::path(text(row,"projection")).parent_path().string()});projected.push_back(Object(row));}
  for(const auto &[key,name]:std::vector<std::pair<std::string,std::string>>{{"formatter","lldb_nex.py"},{"dap_adapter","nex_dap.py"}}){auto bytes=readFile(resourceFile("debug/"+name));if(base.getString(key+"_hash")!=hash(bytes))fail("debug script differs from matching compiler resources");base[key+"_sha256"]=sha(bytes);}
  const auto root=Object(*owners.at(catalog.ownerImage));
  std::sort(codeImages.begin(),codeImages.end(),[](const JSON &a,const JSON &b){return a.getAsObject()->getString("component")<b.getAsObject()->getString("component");});
  Object view{{"schema","nex.task-debug-view/2"},{"abi",2},{"registry_abi",1},{"catalog_symbol","nex_task_debug_catalog_v2"},{"marker_symbol","nex_task_debug_stop_marker"},{"metadata_hash",nativeTaskDebugMetadataHash(catalog,sources)},
    {"image_sha256",text(root,"sha256")},{"image_uuid",text(root,"uuid")},{"catalog_hash",info.catalogHash},{"source_union_hash",info.sourceUnionHash},{"catalog",nativeTaskDebugCatalogJSON(catalog)},{"source_union",nativeTaskDebugSourceUnionJSON(sources)},
    {"runtime_image",std::move(runtimeImage)},{"images",std::move(codeImages)},{"registries",std::move(registries)},{"deadline_advances_while_stopped",true},{"maximum_codes",16384},{"maximum_points",262144},{"maximum_bindings",65536},{"maximum_visible_bindings",1048576}};
  base["schema"]="nex.debug/3";base["expression_protocol"]="nex.task-debug-expression/2";base["task_debug"]=std::move(view);base["functions"]=std::move(functions);base["sources"]=std::move(projected);base["source_map"]=std::move(maps);Array types;for(const auto &name:heap)types.push_back(name);base["heap_types"]=std::move(types);return base;
}

Array relocateNativeTaskDebugOwnedImages(const Object &rawManifest,const Array &imageMappings,
    const std::string &rawDirectory,const std::string &publishedDirectory){
  auto owned=rawManifest.getArray("owned_images");
  if(!owned||owned->size()>129)fail("invalid original owned debug image inventory");
  const auto original=fs::path(text(rawManifest,"program")).parent_path();
  const auto published=fs::absolute(publishedDirectory).lexically_normal();
  std::map<std::string,const Object*> inputs,outputs;
  for(const auto &value:imageMappings){auto mapping=value.getAsObject();
    auto input=mapping?mapping->getObject("input"):nullptr;
    auto output=mapping?mapping->getObject("output"):nullptr;
    if(!input||!output||!outputs.emplace(text(*input,"path"),output).second)fail("invalid owned debug image mapping");
    inputs.emplace(text(*input,"path"),input);
  }
  Array result;std::set<std::string> seen;size_t symbolCount=0;
  for(const auto &value:*owned){auto record=value.getAsObject();
    if(!record||!seen.insert(text(*record,"path")).second||
       (record->getString("kind")!="library"&&record->getString("kind")!="runtime")||
       !outputs.contains(text(*record,"path")))fail("owned debug image has no physical mapping");
    auto row=Object(*record);const auto &output=*outputs.at(text(row,"path"));
    const auto &input=*inputs.at(text(row,"path"));
    for(auto key:{"key","hash","sha256","uuid"})if(row.getString(key)!=input.getString(key))fail("original owned debug image pin differs");
    if(row.getString("key")!=output.getString("key")||
       (row.getString("kind")=="runtime")!=(output.getString("kind")=="runtime"))fail("owned debug image identity differs");
    for(auto key:{"path","hash","sha256","uuid"})row[key]=text(output,key);
    auto symbols=record->getArray("symbols");if(!symbols)fail("missing owned debug symbols");Array relocated;
    for(const auto &symbol:*symbols){auto entry=symbol.getAsObject();if(!entry||entry->size()!=2||++symbolCount>8192)fail("invalid owned debug symbol inventory");
      auto path=fs::path(text(*entry,"path"));auto relative=path.lexically_relative(original);
      if(!path.is_absolute()||path.lexically_normal()!=path||relative.empty()||relative.begin()->string()!="images")fail("owned debug symbol escaped original namespace");
      if(hash(read(rawDirectory,relative.string(),512*1048576))!=text(*entry,"hash"))fail("owned debug symbol bytes differ");
      auto fresh=Object(*entry);fresh["path"]=(published/relative).string();relocated.push_back(std::move(fresh));
    }
    row["symbols"]=std::move(relocated);result.push_back(std::move(row));
  }
  return result;
}

NativeTaskDebugCheckedSources validateNativeTaskDebugManifest(const Object &manifest,const std::string &directory){
  if(manifest.getString("artifact_directory")!=fs::absolute(directory).lexically_normal().string())fail("debug raw namespace differs from manifest directory");
  auto view=manifest.getObject("task_debug");if(manifest.getString("schema")!="nex.debug/3"||manifest.getString("expression_protocol")!="nex.task-debug-expression/2"||manifest.getString("compiler_build")!=NEX_BUILD_ID||!view||view->getString("schema")!="nex.task-debug-view/2"||view->getInteger("abi")!=2||view->getInteger("registry_abi")!=1||view->getString("catalog_symbol")!="nex_task_debug_catalog_v2"||view->getString("marker_symbol")!="nex_task_debug_stop_marker"||view->getBoolean("deadline_advances_while_stopped")!=true)fail("provider debug manifest discriminator differs");
  auto catalogValue=view->get("catalog"),sourcesValue=view->get("source_union");auto images=view->getArray("images");auto runtime=view->getObject("runtime_image");if(!catalogValue||!sourcesValue||!images||!runtime)fail("provider debug manifest omitted its checked closure");
  auto catalog=parseNativeTaskDebugCatalog(*catalogValue);auto sources=parseNativeTaskDebugSourceUnion(*sourcesValue);auto info=nativeTaskDebugInfo(catalog,sources);
  if(view->getString("catalog_hash")!=info.catalogHash||view->getString("source_union_hash")!=info.sourceUnionHash||view->getString("metadata_hash")!=nativeTaskDebugMetadataHash(catalog,sources))fail("provider debug semantic closure differs");
  std::map<std::string,std::string> bundles;for(const auto &source:sources.components)bundles.emplace(source.component,read(directory,source.bundleFile,16*1048576));
  auto checked=validateNativeTaskDebugSources(catalog,sources,bundles);
  for(const auto &value:*images){auto row=value.getAsObject();if(!row)fail("invalid debug physical owner");physicalImage(*row,false);}physicalImage(*runtime,true);
  auto rawValue=parse(read(directory,"debug.json",8*1048576));auto rawManifest=rawValue.getAsObject();if(!rawManifest||rawManifest->getString("schema")!="nex.debug/3")fail("missing original provider debug manifest");
  if(auto relocation=manifest.getObject("relocation")){
    if(relocation->size()!=2||relocation->getString("path")!="debug-relocation.json")fail("invalid debug relocation reference");auto receiptValue=parse(read(directory,"debug-relocation.json",16*1048576));auto receipt=receiptValue.getAsObject();if(!receipt||receipt->size()!=8||receipt->getString("schema")!="nex.task-debug-relocation/1"||receipt->getString("compiler_build")!=NEX_BUILD_ID||receipt->getString("build_key")!=manifest.getString("build_key")||receipt->getString("artifact_directory")!=directory||receipt->getBoolean("metadata_rewritten")!=false||relocation->getString("hash")!=hash(json(Object(*receipt),false)))fail("debug relocation receipt identity differs");
    auto buildValue=parse(read(directory,"build.json",8*1048576));auto build=buildValue.getAsObject();auto files=receipt->getArray("raw_files"),mappings=receipt->getArray("images");if(!build||!files||!mappings||build->getString("compiler_build")!=NEX_BUILD_ID||build->getString("key")!=manifest.getString("build_key"))fail("relocated raw build identity differs");
    auto originalProgram=rawManifest->getString("program");if(!originalProgram||receipt->getString("original_directory")!=fs::path(originalProgram->str()).parent_path().string())fail("original debug program/directory missing or different");std::vector<std::string> names{fs::path(originalProgram->str()).filename().string(),"program.mlir","program.ll","compilation.json","build.json","source-bundle.json"};auto inputs=nativeCompletionInputs(*build);names.insert(names.end(),inputs.begin(),inputs.end());names.push_back("complete");if(names.size()!=files->size())fail("debug relocation raw input count differs");std::string completed=text(*build,"key");
    for(size_t i=0;i<names.size();++i){auto row=(*files)[i].getAsObject();auto bytes=read(directory,names[i],512*1048576);if(!row||row->size()!=3||row->getString("path")!=names[i]||row->getString("hash")!=hash(bytes)||row->getInteger("bytes")!=int64_t(bytes.size()))fail("debug relocation raw byte pin differs");if(names[i]!="complete")completed+=hash(bytes);}if(read(directory,"complete",1024)!=hash(completed)+"\n")fail("relocated raw completion differs");
    auto oldView=rawManifest->getObject("task_debug");if(!oldView||!oldView->getArray("images")||!oldView->getObject("runtime_image")||oldView->getString("metadata_hash")!=view->getString("metadata_hash")||*oldView->get("catalog")!=*view->get("catalog")||*oldView->get("source_union")!=*view->get("source_union")||mappings->size()!=images->size()+(catalog.mode==NativeTaskLinkageMode::Static?0:1))fail("debug relocation changed source metadata");
    std::map<std::string,const Object*> originalImages;for(const auto &value:*oldView->getArray("images")){auto row=value.getAsObject();originalImages.emplace(text(*row,"path"),row);}originalImages[text(*oldView->getObject("runtime_image"),"path")]=oldView->getObject("runtime_image");std::map<std::string,const Object*> outputImages;for(const auto &value:*images){auto row=value.getAsObject();outputImages.emplace(text(*row,"path"),row);}outputImages[text(*runtime,"path")]=runtime;std::set<std::string> seenOriginal,seenOutput;
    for(const auto &value:*mappings){auto mapping=value.getAsObject();auto input=mapping?mapping->getObject("input"):nullptr;auto output=mapping?mapping->getObject("output"):nullptr;if(!mapping||mapping->size()!=2||!input||!output||!originalImages.contains(text(*input,"path"))||!outputImages.contains(text(*output,"path"))||json(Object(*input),false)!=json(Object(*originalImages.at(text(*input,"path"))),false)||json(Object(*output),false)!=json(Object(*outputImages.at(text(*output,"path"))),false))fail("debug relocation physical image mapping differs");
      auto name=fs::path(text(*input,"path")).filename().string();auto relative=text(*input,"kind")=="application"?name:"images/"+name;auto bytes=read(directory,relative,512*1048576);if(hash(bytes)!=text(*input,"hash")||sha(bytes)!=text(*input,"sha256")||nativeImageUUID(closed(directory,relative).string())!=text(*input,"uuid")||input->get("component")==nullptr||output->get("component")==nullptr||*input->get("component")!=*output->get("component")||input->getString("key")!=output->getString("key")||input->getString("kind")!=output->getString("kind"))fail("debug relocation raw image provenance differs");seenOriginal.insert(text(*input,"path"));seenOutput.insert(text(*output,"path"));}
    if(seenOriginal.size()!=originalImages.size()||seenOutput.size()!=outputImages.size())fail("debug relocation omitted a physical owner");
    if(rawManifest->get("owned_images")){
      auto expectedOwned=relocateNativeTaskDebugOwnedImages(*rawManifest,*mappings,directory,directory);
      if(!manifest.getArray("owned_images")||JSON(Array(*manifest.getArray("owned_images")))!=JSON(std::move(expectedOwned)))fail("relocated owned debug images/symbols differ from raw provenance");
    }else if(manifest.get("owned_images"))fail("relocation invented an owned debug image inventory");
  }else if(json(Object(manifest),false)!=json(Object(*rawManifest),false))fail("debug manifest changed without a separate relocation receipt");
  auto expected=finalizeNativeTaskDebugManifest(Object(manifest),catalog,sources,bundles,Array(*images),Object(*runtime));
  for(const auto *key:{"functions","task_debug","sources","source_map","formatter_sha256","dap_adapter_sha256"})if(!manifest.get(key)||json(JSON(*manifest.get(key)),false)!=json(JSON(*expected.get(key)),false))fail("provider debug manifest differs from checked source/physical ownership");
  for(const auto &value:*expected.getArray("sources")){const auto &row=*value.getAsObject();auto file=fs::path(text(row,"projection"));if(hash(read(file.parent_path(),file.filename().string(),16*1048576))!=text(row,"hash"))fail("immutable debug source projection differs");}
  return checked;
}

Object inspectNativeTaskDebugBuildInputs(const BuildResult &built){
  auto folder=fs::path(built.executable).parent_path();auto value=parse(read(folder,"build.json",8*1048576));auto meta=value.getAsObject();if(!meta||meta->getString("key")!=built.key||meta->getString("compiler_build")!=NEX_BUILD_ID||meta->getString("completion_schema")!="nex.native-completion/7")fail("debug launch requires its matching completed provider build");
  std::string completion=built.key;Object pins;
  auto pinned=[&](const std::string &name,uint64_t limit=256*1048576){auto bytes=read(folder,name,limit);pins[name]=hash(bytes);return bytes;};
  for(const auto &name:{fs::path(built.executable).filename().string(),std::string("program.mlir"),std::string("program.ll"),std::string("compilation.json"),std::string("build.json"),std::string("source-bundle.json")})completion+=hash(pinned(name));
  auto names=nativeCompletionInputs(*meta);for(const auto &name:names)completion+=hash(pinned(name));if(read(folder,"complete",1024)!=hash(completion)+"\n")fail("completed provider debug input changed");
  auto obj=[&](const std::string &name){auto v=parse(pinned(name));auto o=v.getAsObject();if(!o)fail("invalid completed debug object");return Object(*o);};
  auto ownJSON=obj("task-provider.json");auto own=parseNativeTaskProvider(JSON(Object(ownJSON)));
  if(!own.debugging||meta->getString("task_provider_hash")!=hash(read(folder,"task-provider.json"))||!meta->get("task_provider")||*meta->get("task_provider")!=JSON(Object(ownJSON))||(own.mode==NativeTaskLinkageMode::SharedFixed&&own.artifact!=NativeTaskArtifactKind::Application)||(own.mode==NativeTaskLinkageMode::Static&&own.codeOnly))fail("debug application provider identity differs");
  auto catalog=parseNativeTaskDebugCatalog(JSON(obj("task-debug-catalog.json")));auto sources=parseNativeTaskDebugSourceUnion(JSON(obj("task-debug-sources.json")));
  auto correlate=[&](const NativeTaskProviderInfo &provider,const NativeTaskDebugCatalog &c,const NativeTaskDebugSourceUnion &u){
    auto info=nativeTaskDebugInfo(c,u);
    const auto artifact=provider.mode==NativeTaskLinkageMode::Static?(provider.codeOnly?NativeTaskArtifactKind::CodeArchive:NativeTaskArtifactKind::Application):provider.artifact;const auto owner=provider.mode==NativeTaskLinkageMode::Static?(provider.codeOnly?std::string{}:provider.component):provider.ownerImage;
    if(!provider.debugging||json(nativeTaskDebugInfoJSON(info),false)!=json(nativeTaskDebugInfoJSON(*provider.debugging),false)||c.mode!=provider.mode||c.artifact!=artifact||c.ownerImage!=owner||u.mode!=provider.mode||u.artifact!=artifact||u.ownerImage!=owner)fail("debug physical mode/sidecar association differs");
    std::map<std::string,std::set<std::string>> definitions;
    for(const auto &component:u.components){auto &set=definitions[component.component];for(const auto &entry:component.definitions)if(!set.insert(entry.name).second)fail("duplicate debug source definition");}
    if(provider.mode==NativeTaskLinkageMode::SharedFixed){std::map<std::string,std::set<std::string>> expected;for(const auto &[name,owner]:provider.definitionOwners)expected[owner].insert(name);if(expected!=definitions)fail("debug source union differs from physical definition owners");}
    else if(!definitions.contains(provider.component)||definitions.at(provider.component)!=provider.definitions||(provider.codeOnly&&definitions.size()!=1))fail("static debug source definition ledger differs");
  };
  correlate(own,catalog,sources);
  auto abi=obj("library-abi.json");auto libraries=abi.getArray("static_libraries");if(!libraries||libraries->size()>128||abi.getString("abi")!=own.cohort)fail("debug static archive inventory differs");
  auto staticExpected=catalog;staticExpected.registries.clear();auto sourceExpected=sources;sourceExpected.components.clear();
  for(const auto &registry:catalog.registries)if(registry.component==own.component)staticExpected.registries.push_back(registry);
  for(const auto &component:sources.components)if(component.component==own.component)sourceExpected.components.push_back(component);
  for(size_t i=0;i<libraries->size();++i){auto row=(*libraries)[i].getAsObject();if(!row)fail("invalid debug static archive record");auto prefix="libraries/"+std::to_string(i);
    for(const auto &[field,suffix]:std::vector<std::pair<std::string,std::string>>{{"path",".a"},{"task_provider_path",".task-provider.json"},{"task_debug_catalog_path",".task-debug-catalog.json"},{"task_debug_sources_path",".task-debug-sources.json"}}){auto name=prefix+suffix;auto pin=field=="path"?"hash":field.substr(0,field.size()-4)+"hash";if(row->getString(field)!=(folder/name).string()||!pins.getString(name)||row->getString(pin)!=pins.getString(name))fail("debug copied static quartet path/raw pin differs");}
    auto stageJSON=obj(prefix+".task-provider.json");auto stage=parseNativeTaskProvider(JSON(Object(stageJSON)));auto c=parseNativeTaskDebugCatalog(JSON(obj(prefix+".task-debug-catalog.json")));auto u=parseNativeTaskDebugSourceUnion(JSON(obj(prefix+".task-debug-sources.json")));correlate(stage,c,u);
    if(stage.cohort!=own.cohort||stage.language!=own.language||!stage.codeOnly||!row->get("task_provider")||*row->get("task_provider")!=JSON(Object(stageJSON)))fail("debug static stage/cohort differs");
    if(own.mode==NativeTaskLinkageMode::Static){for(auto registry:c.registries){registry.ownerImage=own.component;staticExpected.registries.push_back(std::move(registry));}for(auto component:u.components){component.ownerImage=own.component;sourceExpected.components.push_back(std::move(component));}}
  }
  if(own.mode==NativeTaskLinkageMode::Static){std::sort(staticExpected.registries.begin(),staticExpected.registries.end(),[](const auto &a,const auto &b){return a.component<b.component;});std::sort(sourceExpected.components.begin(),sourceExpected.components.end(),[](const auto &a,const auto &b){return a.component<b.component;});if(json(nativeTaskDebugCatalogJSON(staticExpected),false)!=json(nativeTaskDebugCatalogJSON(catalog),false)||json(nativeTaskDebugSourceUnionJSON(sourceExpected),false)!=json(nativeTaskDebugSourceUnionJSON(sources),false))fail("static debug closure differs from actual captured archives");}
  auto application=pinned(fs::path(built.executable).filename().string());
  if(own.mode==NativeTaskLinkageMode::SharedFixed){
    if(!own.image||own.image->key!=built.key||own.image->digest!=hash(application)||own.image->sha256!=sha(application)||own.image->uuid!=nativeImageUUID(built.executable))fail("debug application physical identity differs");
    auto inputs=obj("image-inputs.json");auto images=inputs.getArray("images"),providers=inputs.getArray("task_providers"),catalogs=inputs.getArray("task_debug_catalogs"),unions=inputs.getArray("task_debug_sources");if(inputs.size()!=6||inputs.getString("schema")!="nex.native-image-inputs/4"||!images||!providers||!catalogs||!unions||providers->size()!=catalogs->size()||providers->size()!=unions->size()||providers->size()+1!=images->size())fail("debug image companion closure differs");
    std::map<std::string,const Object*> providerRows,catalogRows,sourceRows;
    for(const auto &[values,rows]:std::vector<std::pair<const Array*,std::map<std::string,const Object*>*>>{{providers,&providerRows},{catalogs,&catalogRows},{unions,&sourceRows}})for(const auto &value:*values){auto row=value.getAsObject();if(!row||!rows->emplace(text(*row,"image"),row).second)fail("duplicate debug image companion");}
    size_t runtimes=0;std::set<std::string> seen;
    for(const auto &value:*images){auto row=value.getAsObject();if(!row)fail("invalid debug image inventory");auto path=fs::path(text(*row,"path"));auto relative="images/"+path.filename().string();if(path!=folder/relative||!seen.insert(relative).second||!pins.getString(relative))fail("unclosed debug image path");auto bytes=pinned(relative,512*1048576);if(row->getString("hash")!=hash(bytes)||row->getString("sha256")!=sha(bytes)||row->getString("uuid")!=nativeImageUUID(path.string())||row->getString("abi")!=own.cohort)fail("debug image physical bytes differ");
      if(row->getString("kind")=="runtime"){++runtimes;if(own.image->runtimeKey!=text(*row,"key")||own.image->runtimeDigest!=hash(bytes))fail("debug runtime identity differs");continue;}
      if(row->getString("kind")!="library"||!providerRows.contains(relative)||!catalogRows.contains(relative)||!sourceRows.contains(relative))fail("unowned debug code image");
      const auto &pr=*providerRows.at(relative),&cr=*catalogRows.at(relative),&sr=*sourceRows.at(relative);auto providerPath=relative+".task-provider.json",catalogPath=relative+".task-debug-catalog.json",sourcePath=relative+".task-debug-sources.json";
      if(pr.size()!=4||cr.size()!=5||sr.size()!=5||pr.getString("path")!=providerPath||cr.getString("path")!=catalogPath||sr.getString("path")!=sourcePath||pr.getString("hash")!=pins.getString(providerPath)||cr.getString("hash")!=pins.getString(catalogPath)||sr.getString("hash")!=pins.getString(sourcePath))fail("debug companion raw pin/path differs");
      auto provider=parseNativeTaskProvider(JSON(obj(providerPath)));auto c=parseNativeTaskDebugCatalog(JSON(obj(catalogPath)));auto u=parseNativeTaskDebugSourceUnion(JSON(obj(sourcePath)));correlate(provider,c,u);
      if(provider.mode!=own.mode||provider.cohort!=own.cohort||provider.artifact!=NativeTaskArtifactKind::SharedImage||!provider.image||provider.component!=text(pr,"component")||provider.component!=text(cr,"component")||provider.component!=text(sr,"component")||provider.image->key!=text(*row,"key")||provider.image->digest!=hash(bytes)||provider.image->sha256!=sha(bytes)||provider.image->uuid!=text(*row,"uuid")||provider.image->runtimeKey!=own.image->runtimeKey||provider.image->runtimeDigest!=own.image->runtimeDigest||cr.getString("catalog_hash")!=provider.debugging->catalogHash||sr.getString("source_union_hash")!=provider.debugging->sourceUnionHash)fail("debug code image/semantic association differs");
      catalog.registries.insert(catalog.registries.end(),c.registries.begin(),c.registries.end());sources.components.insert(sources.components.end(),u.components.begin(),u.components.end());
    }
    if(runtimes!=1)fail("debug closure requires exactly one runtime");
    std::sort(catalog.registries.begin(),catalog.registries.end(),[](const auto &a,const auto &b){return a.component<b.component;});std::sort(sources.components.begin(),sources.components.end(),[](const auto &a,const auto &b){return a.component<b.component;});
  }
  auto info=nativeTaskDebugInfo(catalog,sources);if(meta->getString("task_debug_catalog")!=info.catalogHash||meta->getString("task_debug_sources")!=info.sourceUnionHash||meta->getString("task_debug_metadata_hash")!=nativeTaskDebugMetadataHash(catalog,sources))fail("debug root joined closure semantic identity differs");
  auto manifest=obj("debug.json");auto view=manifest.getObject("task_debug");if(!view||!view->get("catalog")||!view->get("source_union")||*view->get("catalog")!=JSON(nativeTaskDebugCatalogJSON(catalog))||*view->get("source_union")!=JSON(nativeTaskDebugSourceUnionJSON(sources)))fail("debug manifest is not the physical closure catalog");
  (void)validateNativeTaskDebugManifest(manifest,folder.string());
  for(const auto &[name,pin]:pins)if(hash(read(folder,name.str(),512*1048576))!=pin.getAsString())fail("debug input changed during validation");
  return Object{{"pins",std::move(pins)},{"build_key",built.key}};
}
}
