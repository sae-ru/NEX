#include "nex/private_task_modules.h"
#include "nex/task_frontend.h"
#include "nex/task_lifetime.h"
#include "nex/task_ir.h"
#include "nex_task_protocol.h"
#include <algorithm>
#include <cctype>
#include <functional>

namespace nex {
namespace {
using Object=llvm::json::Object;
using Array=llvm::json::Array;
[[noreturn]] void fail(const std::string &message){throw Error("E_EXCEPTION_MODULE",message);}
std::string required(const Object &o,const char *key){auto s=o.getString(key);if(!s||s->empty()||s->contains('\0'))fail(std::string("missing private module field ")+key);return s->str();}
std::set<std::string> strings(const Object &o,const char *key){auto a=o.getArray(key);if(!a||a->size()>4096)fail(std::string("invalid private module array ")+key);std::set<std::string> result;for(const auto &v:*a){auto s=v.getAsString();if(!s||s->empty()||s->contains('\0')||!result.insert(s->str()).second)fail(std::string("invalid or repeated ")+key);}return result;}
Array array(const std::set<std::string> &values){Array result;for(const auto &s:values)result.push_back(s);return result;}
bool componentName(const std::string &s){return !s.empty()&&s.size()<=64&&std::all_of(s.begin(),s.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-';});}
std::string unit(const Program &p,const Function &f){if(p.units.contains(f.unit))return f.unit;if(p.units.contains(f.span.file))return f.span.file;fail("function has no checked source unit: "+f.name);}
void closure(const Program &p,const std::string &name,std::set<std::string> &seen){const auto &f=p.function(name);if(!seen.insert(f.name).second)return;for(const auto &dependency:f.dependencies)closure(p,dependency,seen);}
std::set<std::string> expand(const Program &p,const std::string &name){const auto &f=p.function(name);if(f.typeParameters.empty())return {f.name};std::set<std::string> result;for(const auto &v:p.functions)if(v.templateName==f.name&&v.typeParameters.empty()&&std::none_of(v.typeArguments.begin(),v.typeArguments.end(),containsParameter))result.insert(v.name);if(result.empty())fail("generic export has no checked concrete instantiation: "+name);return result;}
Object context(const Program &p,const std::string &entry){const auto &f=p.function(entry);auto root=unit(p,f);std::set<std::string> selected;std::function<void(const std::string &)> visit=[&](const std::string &key){if(!selected.insert(key).second)return;for(const auto &i:p.units.at(key).imports)visit(i.target);};visit(root);Array units;for(const auto &key:selected){const auto &u=p.units.at(key);units.push_back(Object{{"unit",key},{"file",u.path},{"source",u.source}});}const auto &u=p.units.at(root);return Object{{"schema","nex.private-task-source/2"},{"file",u.path},{"source",u.source},{"entry_unit",root},{"units",std::move(units)}};}
Object signature(const Program &p,const Function &f){
 Array parameters,effects,arguments,captures;Object types;std::set<std::string> visited;
 std::function<void(const Type &)> type=[&](const Type &t){if(t.element)type(*t.element);for(const auto &a:t.arguments)type(a);if(t.kind==Type::Record&&p.hasStructure(t.name)&&visited.insert(t.name).second){const auto &s=p.structure(t.name);types[t.name]=canonical(s);for(const auto *field:s.members())type(field->type);}};
 for(const auto &v:f.params){parameters.push_back(typeName(v.type));type(v.type);}type(f.result);for(const auto &v:f.typeArguments){arguments.push_back(typeName(v));type(v);}for(const auto &v:f.effects)effects.push_back(v);for(const auto &v:f.captures){captures.push_back(Object{{"name",v.name},{"type",typeName(v.type)}});type(v.type);}
 return Object{{"schema","nex.private-task-signature/1"},{"language","0.25-prototype"},{"parameters",std::move(parameters)},{"result",typeName(f.result)},{"effects",std::move(effects)},{"realm",f.realm},{"captures",std::move(captures)},{"type_arguments",std::move(arguments)},{"types",std::move(types)}};
}
Object witnesses(const Program &p,const Function &f){
 Object result;
 std::function<void(E)> expression=[&](E e){if(!e)return;
  if(!e->implementation.empty()){
   auto implementation=std::find_if(p.implementations.begin(),p.implementations.end(),[&](const auto &i){return i.name==e->implementation;});
   if(implementation==p.implementations.end())fail("checked trait witness is absent: "+e->implementation);
   auto trait=std::find_if(p.traits.begin(),p.traits.end(),[&](const auto &t){return t.name==implementation->trait;});
   if(trait==p.traits.end())fail("checked trait contract is absent: "+implementation->trait);
   Array arguments;for(const auto &t:e->traitArguments)arguments.push_back(typeName(t));
   Object row{{"contract",e->traitContract},{"trait",trait->name},{"trait_hash",hash(json(canonical(*trait),false))},{"implementation",implementation->name},{"implementation_hash",hash(json(canonical(*implementation),false))},{"implementation_unit",implementation->unit},{"arguments",std::move(arguments)},{"target",e->text},{"target_signature",signature(p,p.function(e->text))}};
   result[hash(json(Object(row),false))]=std::move(row);
  }
  for(auto a:e->args)expression(a);
 };
 std::function<void(const std::vector<S>&)> block=[&](const auto &body){for(auto s:body){expression(s->expr);childBlocks(s,block);}};block(f.body);return result;
}
Object instance(const Program &p,const Function &f){
 auto found=p.functionTemplates.find(f.templateName);if(found==p.functionTemplates.end())fail("checked generic template is absent: "+f.templateName);
 Array arguments;for(const auto &t:f.typeArguments)arguments.push_back(typeName(t));
 return Object{{"template",f.templateName},{"template_public",found->second.exported},{"unit",unit(p,f)},{"template_hash",hash(json(canonical(found->second),false))},{"template_source_hash",hash(p.definition(found->second))},{"arguments",std::move(arguments)},{"function_hash",hash(json(canonical(f),false))},{"signature",signature(p,f)},{"trait_witnesses",witnesses(p,f)}};
}
bool concreteInstance(const Function &f){return !f.templateName.empty()&&f.typeParameters.empty()&&!f.traitSignature&&!f.closure&&!f.foreign&&std::none_of(f.typeArguments.begin(),f.typeArguments.end(),containsParameter);}
struct Component {
 std::string name,entry,linkage;
 bool application=false;
 std::set<std::string> units,exports,dependencies,complete,definitions,publicExports,supportExports,requestedInstances;
 std::map<std::string,std::set<std::string>> instanceFamilies;
 std::map<std::string,std::string> importKinds;
 std::map<std::string,NativeTaskExport> imports;
 NativeTaskFileRequirements files;
 bool foreign=false;
 Object record;
};
struct Checked {
 std::string application,mode,host="application",instrumentation="none";
 bool mixed=false,specialized=false,hosted=false,measured=false,debugging=false;
 uint64_t timeoutMs=5000;
 std::map<std::string,Component> components;
 std::map<std::string,std::string> owners;
 std::map<std::string,std::string> instanceOwners;
 std::vector<std::string> order;
 Object plan;
};
int64_t requirements(const Program &,const Function &f,const Component &c){
 int64_t result=0;if(f.effects.contains("task"))result|=nexrt::taskCodeDeclaredTask;if(f.realm=="server")result|=nexrt::taskCodeServer;if(f.effects.contains("throw"))result|=nexrt::taskCodeDeclaredThrow;
 if(f.effects.contains("fs")){result|=nexrt::taskCodeDeclaredFs;if((result&7)==7)result|=nexrt::taskCodeFileRead|nexrt::taskCodeFileWrite|nexrt::taskCodeFileStream;}
 if(f.effects.contains("ffi")){result|=nexrt::taskCodeDeclaredFfi;if(f.effects.contains("task")&&f.realm=="server")result|=nexrt::taskCodeForeign;}
 if(c.files.reads)result|=nexrt::taskCodeImageFileRead;if(c.files.writes)result|=nexrt::taskCodeImageFileWrite;if(c.files.streams)result|=nexrt::taskCodeImageFileStream;if(c.foreign)result|=nexrt::taskCodeImageForeign;
 return result;
}
NativeTaskExport surface(const Program &p,const Function &f,const Component &c){auto description=signature(p,f);auto sign=hash(json(Object(description),false));auto contract=hash(json(Object{{"signature",std::move(description)},{"function",canonical(f)},{"source",hash(p.definition(f))}},false));return {contract,sign,nativeSymbol(f.name)+"__task_code_address",requirements(p,f,c)};}
Object exportJSON(const NativeTaskExport &f){return Object{{"contract",f.contract},{"signature",f.signature},{"accessor",f.accessor},{"requirements",f.requirements}};}
Checked checked(const Program &p,const Object &architecture){
 if(!sourceExceptionTasksPrototype(p)||p.units.empty())fail("private source modules require an explicit checked025 multi-unit source context");
 const auto schema=architecture.getString("schema");
 const bool debugging=schema=="nex.private-task-architecture/6";
 const bool measured=schema=="nex.private-task-architecture/5";
 const bool hosted=debugging||measured||schema=="nex.private-task-architecture/4";
 if(architecture.size()!=(debugging?7:measured?6:hosted?5:4)||(schema!="nex.private-task-architecture/1"&&schema!="nex.private-task-architecture/2"&&schema!="nex.private-task-architecture/3"&&!hosted))fail("expected private task architecture/1 through /6");
 Checked result;result.measured=measured;result.debugging=debugging;result.hosted=hosted;result.specialized=hosted||schema=="nex.private-task-architecture/3";result.mixed=result.specialized||schema=="nex.private-task-architecture/2";if(hosted){result.host=required(architecture,"host");if(result.host!="http"&&result.host!="application")fail("unknown private root host");}if(measured){result.instrumentation=required(architecture,"instrumentation");if(result.instrumentation!="profile")fail("private architecture/5 requires explicit profile instrumentation");}if(debugging){result.instrumentation=required(architecture,"instrumentation");auto timeout=architecture.getInteger("debug_timeout_ms");if(result.instrumentation!="debug"||!timeout||*timeout<1||*timeout>3600000)fail("private architecture/6 requires debug instrumentation and timeout1..3600000ms");result.timeoutMs=*timeout;}result.mode=required(architecture,"mode");if(result.mixed?result.mode!="mixed-fixed":result.mode!="static"&&result.mode!="shared-fixed")fail("private module linkage does not match its architecture schema");result.application=required(architecture,"application");auto rows=architecture.getObject("components");if(!rows||rows->empty()||rows->size()>128)fail("invalid private components");
 for(const auto &[name,value]:*rows){auto o=value.getAsObject();auto key=name.str();if(!componentName(key)||!o||o->size()!=(result.specialized?6:result.mixed?5:4))fail("invalid private component");Component c;c.name=key;c.application=key==result.application;c.linkage=result.mixed?required(*o,"linkage"):c.application?"application":result.mode=="static"?"static":"shared";if(c.application?c.linkage!="application":c.linkage!="static"&&c.linkage!="shared")fail("private component linkage does not match its application/provider role");c.units=strings(*o,"units");c.dependencies=strings(*o,"dependencies");c.entry=required(*o,"entry");if(result.specialized)c.requestedInstances=strings(*o,"instantiations");if(c.units.empty())fail("private component has no source units");for(const auto &key:c.units)if(!p.units.contains(key)||!result.owners.emplace(key,c.name).second)fail("source unit is missing or has multiple machine owners: "+key);
  auto entries=expand(p,c.entry);if(c.application&&entries.size()!=1)fail("application entry must be concrete");c.entry=*entries.begin();for(const auto &name:strings(*o,"exports")){auto selected=expand(p,name);c.exports.insert(selected.begin(),selected.end());}if(c.application&&!c.exports.empty())fail("private application cannot be a provider");if(!c.application)c.exports.insert(entries.begin(),entries.end());c.publicExports=c.exports;result.components.emplace(c.name,std::move(c));
 }
 if(!result.components.contains(result.application)||result.owners.size()!=p.units.size())fail("application or checked source ownership is incomplete");
 std::map<std::string,int> states;std::function<void(const std::string &)> visit=[&](const std::string &name){if(!result.components.contains(name))fail("missing component dependency: "+name);if(states[name]==2)return;if(states[name]==1)fail("cyclic private component dependency");states[name]=1;for(const auto &d:result.components.at(name).dependencies){if(d==result.application)fail("provider cannot depend on application");visit(d);}states[name]=2;result.order.push_back(name);};visit(result.application);if(result.order.size()!=result.components.size())fail("private architecture contains components outside the application closure");
 auto sourceOwner=[&](const Function &f)->const std::string &{return result.owners.at(unit(p,f));};
 auto machineOwner=[&](const Function &f)->std::string{auto found=result.instanceOwners.find(f.name);return found==result.instanceOwners.end()?sourceOwner(f):found->second;};
 if(result.specialized){
  // Resolve every explicit selector before walking any family, so traversal
  // order cannot choose the owner of a shared concrete specialization.
  for(auto &[name,c]:result.components)for(const auto &selector:c.requestedInstances){
   auto found=std::find_if(p.functions.begin(),p.functions.end(),[&](const auto &f){return f.name==selector;});
   if(found==p.functions.end()||!concreteInstance(*found))fail("instantiation selector is not an existing checked concrete generic function: "+selector);
   if(sourceOwner(*found)!=name&&(!found->exported||!c.dependencies.contains(sourceOwner(*found))))fail("external instantiation requires a public template and direct source component dependency: "+selector);
   if(!result.instanceOwners.emplace(selector,name).second)fail("concrete instantiation has multiple machine owners: "+selector);
  }
  for(auto &[name,c]:result.components)for(const auto &root:c.requestedInstances){
   auto &family=c.instanceFamilies[root];std::set<std::string> seen;
   std::function<void(const std::string &)> collect=[&](const std::string &key){
    if(!seen.insert(key).second)return;const auto &f=p.function(key);if(f.foreign)return;
    auto explicitOwner=result.instanceOwners.find(key);
    if(explicitOwner!=result.instanceOwners.end()&&explicitOwner->second!=name){
     if(result.components.at(explicitOwner->second).requestedInstances.contains(key))return;
     fail("instantiation families require different owners for one concrete definition: "+key);
    }
    const bool generic=concreteInstance(f);
    const bool captured=f.closure&&family.contains(f.closureOwner);
    if(key!=root&&generic&&sourceOwner(f)!=name&&result.components.at(sourceOwner(f)).publicExports.contains(key)&&explicitOwner==result.instanceOwners.end())return;
    if(generic||captured){
     if(sourceOwner(f)!=name||key==root)result.instanceOwners.emplace(key,name);
    }else if(machineOwner(f)!=name)return;
    family.insert(key);for(const auto &callee:f.dependencies)collect(callee);
   };collect(root);
  }
 }
 auto familyMember=[&](const Component &c,const std::string &function){return std::any_of(c.instanceFamilies.begin(),c.instanceFamilies.end(),[&](const auto &family){return family.second.contains(function);});};
 auto includeRoots=[&](Component &c,const std::set<std::string> &roots){for(const auto &root:roots){(void)analyzeTaskLifetimes(p,root);closure(p,root,c.complete);}for(const auto &function:c.complete){const auto &f=p.function(function);detail::validatePrivateTaskModuleFunction(p,f);if(!f.foreign&&machineOwner(f)==c.name)c.definitions.insert(function);}};
 for(auto &[name,c]:result.components){
  detail::validatePrivateTaskModuleEntry(p,c.entry,c.application,result.host=="http"&&c.application);
  if(!c.units.contains(unit(p,p.function(c.entry))))fail("component entry is not locally owned: "+c.entry);
  for(const auto &key:c.units)for(const auto &import:p.units.at(key).imports){auto owner=result.owners.at(import.target);if(owner!=name&&!c.dependencies.contains(owner))fail("source import lacks its direct architecture dependency: "+key+" -> "+owner);}
  auto roots=c.publicExports;roots.insert(c.entry);for(const auto &root:roots){const auto &f=p.function(root);if(f.foreign||f.closure||!f.captures.empty()||!f.typeParameters.empty()||(!c.application&&!f.exported)||machineOwner(f)!=name||(!c.units.contains(unit(p,f))&&!(result.specialized&&c.requestedInstances.contains(root))))fail("provider export must be a locally emitted public concrete function: "+root);}
  roots.insert(c.requestedInstances.begin(),c.requestedInstances.end());includeRoots(c,roots);
 }
 if(result.specialized){
  bool changed=true;while(changed){changed=false;
   for(const auto &[name,c]:result.components)for(const auto &function:c.definitions)if(familyMember(c,function))for(const auto &dependency:p.function(function).dependencies){
    const auto &f=p.function(dependency);if(f.foreign||machineOwner(f)==name)continue;
    auto &provider=result.components.at(machineOwner(f));if(provider.publicExports.contains(f.name))continue;
    const bool localInstance=concreteInstance(f)&&provider.requestedInstances.contains(f.name)&&sourceOwner(f)==provider.name;
    if(f.closure||(concreteInstance(f)&&!localInstance))fail("external instantiation-family call requires a selected concrete export or an origin-owned support instance: "+f.name);
    if(!c.dependencies.contains(provider.name))fail("instantiation support requires a direct machine dependency: "+provider.name);
    if(provider.supportExports.insert(f.name).second)changed=true;
   }
   if(changed)for(auto &[name,c]:result.components){(void)name;includeRoots(c,c.supportExports);}
  }
 }
 for(auto &[name,c]:result.components){(void)name;c.exports.insert(c.supportExports.begin(),c.supportExports.end());c.exports.insert(c.requestedInstances.begin(),c.requestedInstances.end());c.files=nativeTaskFileRequirements(p,c.complete);for(const auto &function:c.complete)if(p.function(function).foreign)c.foreign=true;}
 for(auto &[name,c]:result.components){
  for(const auto &function:c.definitions)for(const auto &dependency:p.function(function).dependencies){const auto &f=p.function(dependency);if(f.foreign)continue;auto owner=machineOwner(f);if(owner==name)continue;if(!c.dependencies.contains(owner))fail("machine call lacks a direct dependency: "+function+" -> "+owner);const auto &provider=result.components.at(owner);const bool support=result.specialized&&familyMember(c,function)&&provider.supportExports.contains(f.name);if(!provider.publicExports.contains(f.name)&&!support)fail("cross-module reference has no selected public export: "+f.name);c.importKinds[f.name]=provider.publicExports.contains(f.name)?"public":"instantiation-support";c.imports.emplace(f.name,surface(p,f,provider));}
  Object definitions,exports,imports;
  for(const auto &function:c.definitions){const auto &f=p.function(function);definitions[function]=Object{{"function_hash",hash(json(canonical(f),false))},{"source_hash",hash(p.definition(f))},{"unit",unit(p,f)},{"signature",signature(p,f)}};}
  for(const auto &function:c.publicExports)exports[function]=exportJSON(surface(p,p.function(function),c));for(const auto &[function,f]:c.imports)imports[function]=exportJSON(f);
  auto sources=context(p,c.entry);auto sourceHash=hash(json(Object(sources),false));
  c.record=Object{{"schema","nex.private-task-module/1"},{"archived",false},{"language","0.25-prototype"},{"compiler_build",NEX_BUILD_ID},{"descriptor_abi",nexrt::taskCodeExceptionHostPrototypeABI},{"descriptor_size",88},{"abi_offset",40},{"mode",result.mode},{"component",name},{"kind",c.application?"application":"code"},{"entry",c.entry},{"units",array(c.units)},{"dependencies",array(c.dependencies)},{"definitions",std::move(definitions)},{"exports",std::move(exports)},{"imports",std::move(imports)},{"source_hash",sourceHash},{"source_context",std::move(sources)},{"file_reads",c.files.reads},{"file_writes",c.files.writes},{"file_streams",c.files.streams},{"foreign",c.foreign}};
  if(result.specialized){
   Object families,instances,selectedWitnesses,support,kinds,descriptors;
   for(const auto &[root,functions]:c.instanceFamilies)families[root]=array(functions);
   for(const auto &function:c.definitions){
    const auto &f=p.function(function);auto &definition=*c.record.getObject("definitions")->getObject(function);definition["source_component"]=sourceOwner(f);definition["machine_component"]=machineOwner(f);
    if(concreteInstance(f))instances[function]=instance(p,f);
    auto selected=witnesses(p,f);if(!selected.empty())selectedWitnesses[function]=std::move(selected);
   }
   for(const auto &function:c.supportExports)support[function]=exportJSON(surface(p,p.function(function),c));
   for(const auto &function:c.requestedInstances)descriptors[function]=exportJSON(surface(p,p.function(function),c));
   for(const auto &[function,kind]:c.importKinds)kinds[function]=kind;
   c.record["instantiation_roots"]=array(c.requestedInstances);c.record["instantiation_families"]=std::move(families);c.record["template_instances"]=std::move(instances);c.record["trait_witnesses"]=std::move(selectedWitnesses);c.record["support_exports"]=std::move(support);c.record["instantiation_descriptors"]=std::move(descriptors);c.record["import_kinds"]=std::move(kinds);
  }
 }
 Object components;bool reads=false,writes=false,streams=false,foreign=false;for(const auto &[name,c]:result.components){components[name]=Object(c.record);reads|=c.files.reads;writes|=c.files.writes;streams|=c.files.streams;foreign|=c.foreign;}Array order;for(const auto &name:result.order)order.push_back(name);
 result.plan=Object{{"schema","nex.private-task-modules/1"},{"archived",false},{"language","0.25-prototype"},{"compiler_build",NEX_BUILD_ID},{"descriptor_abi",nexrt::taskCodeExceptionHostPrototypeABI},{"mode",result.mode},{"application",result.application},{"source_hash",hash(json(sourceExceptionTaskContext(p),false))},{"load_order",std::move(order)},{"components",std::move(components)},{"runtime_requirements",Object{{"file_reads",reads},{"file_writes",writes},{"file_streams",streams},{"foreign",foreign}}}};
 if(result.mixed){
  // Source ownership is not physical image ownership: a static component is
  // absorbed at its next application/shared frontier. Deduplicate a diamond
  // within one image, but reject two loaded incarnations of the same component.
  std::map<std::string,std::string> imageOwners;
  Object images,definitionOwners;Array imageOrder;
  for(const auto &root:result.order){
   const auto &owner=result.components.at(root);if(owner.linkage=="static")continue;
   std::set<std::string> selected,dynamic;
   std::function<void(const std::string &)> frontier=[&](const std::string &name){
    if(!selected.insert(name).second)return;
    auto [found,inserted]=imageOwners.emplace(name,root);
    if(!inserted&&found->second!=root)fail("static component has multiple loaded machine images: "+name+" in "+found->second+" and "+root);
    for(const auto &dependency:result.components.at(name).dependencies){
     if(result.components.at(dependency).linkage=="shared")dynamic.insert(dependency);
     else frontier(dependency);
    }
   };frontier(root);
   Array statics,dependencies;Object definitions;
   for(const auto &name:result.order)if(selected.contains(name)){
    if(name!=root)statics.push_back(name);
    const auto &c=result.components.at(name);
    for(const auto &function:c.definitions){
     if(definitionOwners.get(function))fail("private load closure repeats a machine definition: "+function);
     definitionOwners[function]=root;
     Object definition{{"source_component",result.specialized?sourceOwner(p.function(function)):name},{"function_hash",hash(json(canonical(p.function(function)),false))}};
     if(result.specialized)definition["machine_component"]=name;
     definitions[function]=std::move(definition);
    }
   }
   for(const auto &name:result.order)if(dynamic.contains(name))dependencies.push_back(name);
   images[root]=Object{{"kind",owner.application?"application":"shared"},{"static_components",std::move(statics)},{"dependencies",std::move(dependencies)},{"definitions",std::move(definitions)}};imageOrder.push_back(root);
  }
  if(imageOwners.size()!=result.components.size())fail("private image ownership is incomplete");
  Object componentImages;
  for(auto &[name,c]:result.components){
   componentImages[name]=imageOwners.at(name);c.record["schema"]=result.debugging?"nex.private-task-module/6":result.measured?"nex.private-task-module/5":result.hosted?"nex.private-task-module/4":result.specialized?"nex.private-task-module/3":"nex.private-task-module/2";c.record["linkage"]=c.linkage;c.record["machine_image"]=imageOwners.at(name);
   if(result.hosted){c.record["entry_kind"]=c.application?result.host:"code";if(c.application&&result.host=="http")c.record["entry_descriptor"]=nativeSymbol(c.entry)+"__task_code_address";}
   (*result.plan.getObject("components"))[name]=Object(c.record);
  }
  result.plan["schema"]=result.debugging?"nex.private-task-modules/6":result.measured?"nex.private-task-modules/5":result.hosted?"nex.private-task-modules/4":result.specialized?"nex.private-task-modules/3":"nex.private-task-modules/2";result.plan["runtime_linkage"]=images.size()>1?"shared":"application";result.plan["images"]=std::move(images);result.plan["component_images"]=std::move(componentImages);result.plan["definition_owners"]=std::move(definitionOwners);result.plan["image_load_order"]=std::move(imageOrder);if(result.hosted)result.plan["host"]=result.host;
  if(result.specialized){Object owners,roots;for(const auto &[function,owner]:result.instanceOwners)owners[function]=owner;for(const auto &[name,c]:result.components)for(const auto &root:c.requestedInstances)roots[root]=name;result.plan["specialization_owners"]=std::move(owners);result.plan["instantiation_roots"]=std::move(roots);}
 }
 if(result.measured){
  Object registries;std::set<std::string> registryNames;size_t count=0,textBytes=0;
  for(auto &[name,c]:result.components){
   const auto key="private_"+hash(name).substr(0,48);if(!registryNames.insert(key).second)fail("private profile registry identity collision");
   Array sites;
   for(const auto &function:c.definitions){const auto &f=p.function(function);const auto keyUnit=unit(p,f);const auto canonicalHash=hash(json(canonical(f),false));const auto file=p.location(f.span);
    ++count;if(count>16384)fail("private profile cohort exceeds16384 source sites");
    for(const auto &text:{f.name,file,canonicalHash}){if(text.size()+1>16777216-textBytes)fail("private profile cohort source text exceeds16MiB");textBytes+=text.size()+1;}
    sites.push_back(Object{{"name",f.name},{"function_hash",canonicalHash},{"function_source_hash",hash(p.definition(f))},{"source_unit_hash",hash(p.units.at(keyUnit).source)},{"unit",keyUnit},{"file",file},{"line",int64_t(f.span.line)},{"source_component",sourceOwner(f)},{"machine_component",c.name},{"machine_image",c.record.getString("machine_image")->str()}});
   }
   Object profile{{"schema","nex.private-task-module-profile/1"},{"registry_abi",1},{"registry_component",key},{"registry_accessor",nativeTaskProfileRegistryAccessor(key)},{"sites",std::move(sites)}};
   profile["catalog_hash"]=hash(json(Object(profile),false));c.record["profiling"]=Object(profile);registries[name]=std::move(profile);(*result.plan.getObject("components"))[name]=Object(c.record);
  }
  result.plan["instrumentation"]=result.instrumentation;result.plan["profiling"]=Object{{"schema","nex.private-task-profile-catalog/1"},{"archived",false},{"language","0.25-prototype"},{"registry_abi",1},{"registries",std::move(registries)},{"site_count",int64_t(count)},{"source_text_bytes",int64_t(textBytes)}};
 }
 if(result.debugging){
  Object registries;size_t codes=0,points=0,bindings=0,visible=0,text=0;std::set<std::string> keys;
  auto addText=[&](const std::string &s){if(s.size()+1>16777216-text)fail("private debug text exceeds16MiB");text+=s.size()+1;};
  for(auto &[name,c]:result.components){
   const auto key="private_"+hash(name).substr(0,48);if(!keys.insert(key).second)fail("private debug registry collision");addText(key);Array rows;
   for(const auto &function:c.definitions){
    const auto &f=p.function(function);const auto keyUnit=unit(p,f);const auto fnHash=hash(json(canonical(f),false)),sourceHash=hash(p.definition(f)),file=p.location(f.span);auto metadata=taskDebugFunctionMetadata(p,f,file);
    if(f.name.size()>4096||file.size()>4096)fail("private debug function/path text exceeds4096 bytes");
    if(++codes>16384)fail("private debug cohort exceeds16384 codes");addText(f.name);addText(fnHash);addText(sourceHash);addText(file);
    auto ps=metadata.getArray("points"),bs=metadata.getArray("bindings");points+=ps->size();bindings+=bs->size();
    for(const auto &b:*bs){const auto &row=*b.getAsObject();if(row.getString("name")->size()>256||row.getString("type")->size()>4096)fail("private debug binding text exceeds reader bounds");addText(row.getString("name")->str());addText(row.getString("type")->str());}
    for(const auto &point:*ps){const auto &row=*point.getAsObject();visible+=row.getArray("visible")->size();addText(row.getString("site")->str());}
    if(points>262144||bindings>65536||visible>1048576)fail("private debug cohort metadata exceeds runtime bounds");
    rows.push_back(Object{{"name",function},{"function_hash",fnHash},{"function_source_hash",sourceHash},{"source_unit_hash",hash(p.units.at(keyUnit).source)},{"unit",keyUnit},{"source_component",sourceOwner(f)},{"machine_component",name},{"machine_image",c.record.getString("machine_image")->str()},{"task_debug",std::move(metadata)}});
   }
   Object table{{"schema","nex.private-task-module-debug/1"},{"registry_abi",1},{"registry_component",key},{"registry_accessor",nativeTaskDebugRegistryAccessor(key)},{"codes",std::move(rows)}};table["metadata_hash"]=hash(json(Object(table),false));c.record["debugging"]=Object(table);registries[name]=std::move(table);(*result.plan.getObject("components"))[name]=Object(c.record);
  }
  if(result.components.size()*56+codes*112+points*72+bindings*40+visible*8+text>67108864)fail("private debug metadata exceeds64MiB");
  result.plan["instrumentation"]="debug";result.plan["debugging"]=Object{{"schema","nex.private-task-debug-catalog/1"},{"archived",false},{"language","0.25-prototype"},{"registry_abi",1},{"catalog_abi",2},{"registries",std::move(registries)},{"code_count",int64_t(codes)},{"point_count",int64_t(points)},{"binding_count",int64_t(bindings)},{"visible_count",int64_t(visible)},{"source_text_bytes",int64_t(text)},{"compiled_timeout_ms",int64_t(result.timeoutMs)}};
 }
 return result;
}
Program reload(const Program &p){return loadSourceExceptionTaskContext(sourceExceptionTaskContext(p));}
}
Object planSourceExceptionTaskModules(const Program &p,const Object &architecture){auto current=reload(p);return checked(current,architecture).plan;}
Object sourceExceptionTaskModuleDebugContext(const Program &input,const Object &architecture){
 auto p=reload(input);auto current=checked(p,architecture);if(!current.debugging)fail("module debug context requires architecture/6");
 const auto &catalog=*current.plan.getObject("debugging");const auto &tables=*catalog.getObject("registries");std::map<std::string,const Object *> ordered;
 for(const auto &[name,value]:tables){const auto &table=*value.getAsObject();ordered[table.getString("registry_component")->str()]=&table;}
 Array functions,summaries,identity;size_t first=0,index=0;
 for(const auto &[key,table]:ordered){const auto &rows=*table->getArray("codes");const auto *owner=rows.empty()?nullptr:rows[0].getAsObject();if(!owner)fail("private code component has no debug code");
  summaries.push_back(Object{{"component",key},{"accessor",table->getString("registry_accessor")->str()},{"owner_image","private_"+hash(owner->getString("machine_image")->str()).substr(0,48)},{"first_code",int64_t(first)},{"code_count",int64_t(rows.size())}});
  size_t local=0;for(const auto &value:rows){auto row=Object(*value.getAsObject());auto metadata=Object(*row.getObject("task_debug"));metadata["site_id"]=int64_t(++first);row["task_debug"]=std::move(metadata);row["registry_index"]=int64_t(index);row["local_site_id"]=int64_t(++local);row["owner_image"]="private_"+hash(row.getString("machine_image")->str()).substr(0,48);auto symbol=nativeSymbol(row.getString("name")->str())+"__task_step";row["native_symbol"]=symbol;row["task_continuation_symbol"]=symbol;functions.push_back(Object(row));identity.push_back(std::move(row));}++index;
 }
 auto sources=sourceExceptionTaskContext(p);auto sourceHash=hash(json(Object(sources),false));
 Object componentKeys;for(const auto &[name,_]:current.components)componentKeys[name]="private_"+hash(name).substr(0,48);
 Object layout{{"component_keys",std::move(componentKeys)},{"application",current.application},{"runtime_linkage",current.plan.getString("runtime_linkage")->str()},{"images",Object(*current.plan.getObject("images"))},{"component_images",Object(*current.plan.getObject("component_images"))}};
 Object result{{"schema","nex.private-task-debug/2"},{"archived",false},{"language","0.25-prototype"},{"runtime_view","nex.runtime-view/3"},{"expression_protocol","nex.private-task-debug-expression/1"},{"compiler_build",NEX_BUILD_ID},{"source_context",std::move(sources)},{"source_hash",sourceHash},{"build_key",hash(sourceHash+json(Object(architecture),false))},{"descriptor_abi","0x4e45585400002502"},{"compiled_timeout_ms",int64_t(current.timeoutMs)},{"module_architecture",Object(architecture)},{"module_plan_hash",hash(json(Object(current.plan),false))},{"module_catalog",Object(catalog)},{"image_plan",std::move(layout)},{"heap_types",Array{}},{"source_map",Array{}},{"functions",std::move(functions)},
  {"task_debug",Object{{"schema","nex.task-debug-view/2"},{"abi",2},{"registry_abi",1},{"catalog_symbol","nex_task_debug_catalog_v2"},{"marker_symbol","nex_task_debug_stop_marker"},{"metadata_hash",hash(json(std::move(identity),false))},{"deadline_advances_while_stopped",true},{"maximum_codes",16384},{"maximum_points",262144},{"maximum_bindings",65536},{"maximum_visible_bindings",1048576},{"registries",std::move(summaries)}}}};
 if(current.host=="http")(*result.getObject("task_debug"))["completion_marker_symbol"]="nex_task_debug_completion_marker";
 return result;
}
Object describeSourceExceptionTaskInstances(const Program &p,const std::string &templateFilter,unsigned offset,unsigned limit){
 auto current=reload(p);if(limit<1||limit>256)fail("instance catalogue limit must be between1 and256");
 if(!templateFilter.empty()&&!current.functionTemplates.contains(templateFilter))fail("unknown checked generic template filter: "+templateFilter);
 std::map<std::string,const Function *> selected;
 for(const auto &f:current.functions)if(concreteInstance(f)&&(templateFilter.empty()||f.templateName==templateFilter))selected.emplace(f.name,&f);
 Object instances;uint64_t index=0;for(const auto &[name,f]:selected){if(index>=offset&&index<uint64_t(offset)+limit)instances[name]=instance(current,*f);++index;}
 const uint64_t next=uint64_t(offset)+instances.size();const bool truncated=next<selected.size();
 return Object{{"schema","nex.private-task-instances/1"},{"archived",false},{"language","0.25-prototype"},{"compiler_build",NEX_BUILD_ID},{"source_hash",hash(json(sourceExceptionTaskContext(current),false))},{"template_filter",templateFilter},{"offset",int64_t(offset)},{"limit",int64_t(limit)},{"total",int64_t(selected.size())},{"next_offset",truncated?llvm::json::Value(int64_t(next)):llvm::json::Value(nullptr)},{"truncated",truncated},{"instances",std::move(instances)}};
}
PrivateTaskModuleEmission emitSourceExceptionTaskModule(const Program &p,const Object &architecture,const std::string &component,bool optimized){
 auto current=reload(p);auto plan=checked(current,architecture);if(!plan.components.contains(component))fail("missing private emission component");const auto &c=plan.components.at(component);detail::PrivateTaskModuleCodegen code;code.entry=c.entry;code.application=c.application;code.http=c.application&&plan.host=="http";code.profiling=plan.measured;code.debugging=plan.debugging;code.timeoutMs=plan.timeoutMs;if(plan.debugging){const auto &debug=*c.record.getObject("debugging");code.debugAccessor=debug.getString("registry_accessor")->str();code.debugComponent=debug.getString("registry_component")->str();}if(plan.measured){const auto &profile=*c.record.getObject("profiling");code.profileAccessor=profile.getString("registry_accessor")->str();code.profileComponent=profile.getString("registry_component")->str();}code.reads=c.files.reads;code.writes=c.files.writes;code.streams=c.files.streams;code.foreign=c.foreign;code.definitions=c.definitions;code.complete=c.complete;code.exports=c.exports;code.imports=c.imports;
 return {detail::emitPrivateTaskModule(current,code,optimized),Object(c.record)};
}
void validateSourceExceptionTaskModule(const Program &p,const Object &architecture,const std::string &component,const Object &record){auto current=reload(p);auto plan=checked(current,architecture);if(!plan.components.contains(component)||json(Object(record),false)!=json(Object(plan.components.at(component).record),false))fail("private module record differs from current checked source and architecture");}
}
