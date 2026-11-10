#include "nex/discovery.h"
#include <algorithm>

namespace nex {
namespace {
std::vector<std::string> pathParts(const std::string &field){
  if(field.empty()||field.size()>256)throw Error("E_OPTION","describe field must contain 1..256 ASCII bytes");
  std::vector<std::string> result;std::string part;
  for(char character:field){
    if(character=='.'){
      if(part.empty())throw Error("E_OPTION","describe field has an empty path component");
      result.push_back(std::move(part));part.clear();
      if(result.size()>=8)throw Error("E_OPTION","describe field has more than 8 path components");
    }else{
      bool letter=(character>='a'&&character<='z')||(character>='A'&&character<='Z')||character=='_';
      bool digit=character>='0'&&character<='9';
      if(!letter&&(!digit||part.empty()))throw Error("E_OPTION","describe fields use ASCII identifier components separated by dots");
      part+=character;
    }
  }
  if(part.empty())throw Error("E_OPTION","describe field has an empty path component");
  result.push_back(std::move(part));return result;
}
}
llvm::json::Value discover(const std::string &kind,const std::string &field,const std::string &toolchain,const std::string &compilerBuild){
  if(kind!="full"&&kind!="index"&&kind!="field")throw Error("E_OPTION","describe kind must be full, index or field");
  if(kind!="field"&&!field.empty())throw Error("E_OPTION","describe --field cannot be combined with another kind");
  auto parts=kind=="field"?pathParts(field):std::vector<std::string>{};
  auto descriptor=describe();
  if(kind=="full")return descriptor;
  llvm::json::Object result{{"schema","nex.discovery/1"},{"language",languageVersion},
    {"toolchain",toolchain},{"compiler_build",compilerBuild},{"descriptor_hash",hash(json(descriptor,false))},{"kind",kind}};
  if(kind=="index"){
    std::vector<std::string> fields;for(const auto &entry:*descriptor.getAsObject())fields.push_back(entry.first.str());
    std::sort(fields.begin(),fields.end());llvm::json::Array names;for(const auto &name:fields)names.push_back(name);
    result["fields"]=std::move(names);result["full_schema"]="nex.language/1";
    result["full_command"]="nex describe --json";result["field_command"]="nex describe --field PATH --json";
    result["guide"]="docs/discovery.md";result["bootstrap_prompt"]="llm/BOOTSTRAP.md";
    result["legacy_fields"]=llvm::json::Array{"features"};
    result["recommended_fields"]=*descriptor.getAsObject()->getObject("features_scope")->get("recommended_fields");
  }else{
    auto *selected=&descriptor;
    for(const auto &part:parts){
      auto *object=selected->getAsObject();if(!object)throw Error("E_OPTION","describe field path traverses a non-object value");
      selected=object->get(part);if(!selected)throw Error("E_OPTION","describe field path does not exist");
    }
    result["field"]=field;result["value"]=std::move(*selected);
    if(field=="features"){result["value_scope"]="legacy_partial_summary";result["value_complete"]=false;result["capability_index_command"]="nex describe --kind index --json";}
  }
  return result;
}
}
