#include "nex/cli.h"
#include <algorithm>
#include <sstream>

namespace nex {
namespace {
bool contains(const std::vector<std::string> &v,const std::string &s){return std::find(v.begin(),v.end(),s)!=v.end();}
llvm::json::Array strings(const std::vector<std::string> &values){
  llvm::json::Array result;for(const auto &value:values)result.push_back(value);return result;
}
void bounded(const llvm::json::Value &value,size_t limit){
  if(json(value).size()>limit)throw Error("E_INTERNAL","compiled CLI projection exceeds its advertised bound");
}
}
llvm::json::Value cliHelp(const std::string &name,const std::string &version,const std::string &build){
  llvm::json::Object result{{"schema","nex.cli-help/1"},{"ok",true},{"language",languageVersion},
    {"compiler",llvm::json::Object{{"version",version},{"build",build}}},
    {"kind",name.empty()?"index":"command"},{"command",name},{"guide","docs/cli.md"},
    {"project_opened",false},{"command_executed",false}};
  if(name.empty()){
    llvm::json::Array commands;
    for(const auto &c:cliCommands())if(!c.hidden)
      commands.push_back(llvm::json::Object{{"name",c.name},{"arguments",c.arguments},{"description",c.description}});
    result["commands"]=std::move(commands);
  }else{
    auto c=cliCommand(name);if(!c)throw Error("E_COMMAND","unknown command '"+name+"'");
    result["arguments"]=c->arguments;result["description"]=c->description;
    result["feature_guide"]="nex guide --kind "+c->guide;
    result["application_arguments"]=c->applicationArguments;
    result["value_combination_rules"]="Existing command handlers and the selected feature guide remain authoritative.";
    llvm::json::Array options;
    for(const auto &key:c->options){
      const auto &o=*cliOption(key);
      llvm::json::Object entry{{"name",o.name},{"takes_value",!o.metavar.empty()},
        {"value",o.metavar},{"aliases",strings(o.aliases)},{"description",o.description}};
      if(auto values=c->choices.find(key);values!=c->choices.end())entry["known_values"]=strings(values->second);
      options.push_back(std::move(entry));
    }
    result["options"]=std::move(options);
  }
  llvm::json::Value value(std::move(result));bounded(value,32768);return value;
}
std::string cliHelpText(const llvm::json::Value &help){
  const auto &o=*help.getAsObject();std::ostringstream text;
  text<<"NEX "<<o.getObject("compiler")->getString("version")->str()<<" (language "<<languageVersion<<")\n";
  auto name=o.getString("command")->str();
  if(name.empty()){
    text<<"Usage: nex COMMAND [OPTIONS]\nUse nex help COMMAND or nex COMMAND --help for bounded command help.\n\n";
    for(const auto &entry:*o.getArray("commands")){
      const auto &c=*entry.getAsObject();text<<"  "<<c.getString("name")->str()<<"  "<<c.getString("description")->str()<<'\n';
    }
  }else{
    text<<"Usage: nex "<<name<<' '<<o.getString("arguments")->str()<<" [OPTIONS]\n"
        <<o.getString("description")->str()<<"\n\nOptions:\n";
    for(const auto &entry:*o.getArray("options")){
      const auto &option=*entry.getAsObject();text<<"  "<<option.getString("name")->str();
      for(const auto &alias:*option.getArray("aliases"))text<<", "<<alias.getAsString()->str();
      auto value=option.getString("value")->str();if(!value.empty())text<<' '<<value;
      text<<"  "<<option.getString("description")->str()<<'\n';
      if(auto values=option.getArray("known_values")){
        text<<"    Known values:";for(const auto &v:*values)text<<' '<<v.getAsString()->str();text<<'\n';
      }
    }
    text<<"\nGuide: "<<o.getString("feature_guide")->str()<<"\nValue combinations retain the guide/handler restrictions.\n";
  }
  auto result=text.str();if(result.size()>16384)throw Error("E_INTERNAL","command help text exceeds 16 KiB");return result;
}
llvm::json::Value cliComplete(const std::vector<std::string> &input){
  if(input.size()>128)throw Error("E_OPTION","completion accepts at most 128 words");
  for(const auto &word:input)if(word.size()>4096)throw Error("E_OPTION","completion word exceeds 4096 bytes");
  auto words=input;if(words.empty())words.push_back("");
  const auto &prefix=words.back();std::vector<std::string> candidates;std::string expects="none",command;
  auto commands=[&]{expects="command";for(const auto &c:cliCommands())if(!c.hidden)candidates.push_back(c.name);};
  if(words.size()==1){
    if(prefix.starts_with("-")){expects="option";candidates={"--help","-h"};}else commands();
  }else if(words.front()=="help")commands();
  else if(auto c=cliCommand(words.front())){
    command=c->name;std::string pending;std::set<std::string> used;bool stopped=false;
    for(size_t i=1;i+1<words.size();++i){
      const auto &word=words[i];
      if(!pending.empty()){pending.clear();continue;}
      if(word=="--"){stopped=true;expects=c->applicationArguments?"application":"none";break;}
      if(word.starts_with("-")){
        const auto *option=cliOption(word);
        if(!option||!contains(c->options,option->name)){stopped=true;break;}
        used.insert(option->name);if(!option->metavar.empty())pending=option->name;
      }
    }
    if(!stopped){
      if(!pending.empty()){
        expects="value";if(auto values=c->choices.find(pending);values!=c->choices.end())candidates=values->second;
      }else if(prefix.starts_with("-")){
        expects="option";for(const auto &name:c->options)if(!used.contains(name)){
          candidates.push_back(name);for(const auto &alias:cliOption(name)->aliases)candidates.push_back(alias);
        }
      }else expects="file_or_symbol";
    }
  }
  std::sort(candidates.begin(),candidates.end());
  candidates.erase(std::unique(candidates.begin(),candidates.end()),candidates.end());
  candidates.erase(std::remove_if(candidates.begin(),candidates.end(),[&](const auto &s){return !s.starts_with(prefix);}),candidates.end());
  llvm::json::Value result=llvm::json::Object{{"schema","nex.cli-completion/1"},{"ok",true},
    {"command",command},{"prefix",prefix},{"expects",expects},{"candidates",strings(candidates)},
    {"filesystem_read",false},{"project_opened",false},{"command_executed",false}};
  bounded(result,16384);return result;
}
std::string cliCompletionScript(const std::string &shell){
  if(shell=="bash")return R"NEX(# NEX completion: source this file in Bash.
_nex_complete() {
  local candidate
  COMPREPLY=()
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] && COMPREPLY+=("$candidate")
  done < <(command nex complete -- "${COMP_WORDS[@]:1:$COMP_CWORD}")
}
complete -o default -F _nex_complete nex
)NEX";
  if(shell=="zsh")return R"NEX(# NEX completion: initialize compinit, then source this file.
_nex_complete() {
  local reply
  local -a candidates args
  args=("${(@)words[2,CURRENT]}")
  if (( CURRENT > 1 )); then args[-1]=$PREFIX; fi
  reply=$(command nex complete -- "${args[@]}")
  if [[ -n "$reply" ]]; then
    candidates=("${(@f)reply}")
    compadd -Q -a candidates
  else
    _files
  fi
}
compdef _nex_complete nex
)NEX";
  if(shell=="fish")return R"NEX(# NEX completion: source this file in fish.
function __nex_candidates
    set -l prior (commandline -opc)
    set -l current (commandline -ct)
    if not set -q current[1]
        set current ''
    end
    command nex complete -- $prior[2..-1] "$current"
end
complete -c nex -a '(__nex_candidates)'
)NEX";
  if(shell=="powershell")return R"NEX(# NEX completion: dot-source this file in PowerShell 7.3 or later.
Register-ArgumentCompleter -Native -CommandName nex -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $prior = @($commandAst.CommandElements | Select-Object -Skip 1 |
        Where-Object { $_.Extent.EndOffset -lt $cursorPosition } |
        ForEach-Object {
            if ($_ -is [System.Management.Automation.Language.StringConstantExpressionAst]) { $_.Value }
            else { $_.Extent.Text }
        })
    $nexWords = @($prior) + @([string]$wordToComplete)
    $result = & nex complete --json -- @nexWords | ConvertFrom-Json
    foreach ($candidate in $result.candidates) {
        [System.Management.Automation.CompletionResult]::new(
            $candidate, $candidate, 'ParameterValue', $candidate)
    }
}
)NEX";
  throw Error("E_OPTION","completion kind must be bash, zsh, fish or powershell");
}
llvm::json::Value cliCapability(){
  return llvm::json::Object{{"help_command","nex help [COMMAND] [--json]"},
    {"command_help","nex COMMAND --help [--json]"},{"help_schema","nex.cli-help/1"},
    {"completion_command","nex completion --kind bash|zsh|fish|powershell [--json]"},
    {"query_command","nex complete [--json] -- WORDS..."},{"query_schema","nex.cli-completion/1"},
    {"script_schema","nex.cli-completion-script/1"},{"guide","docs/cli.md"},
    {"parser_option_types_from_catalogue",true},{"compiled",true},{"project_opened",false},
    {"quiet_flag","--quiet"},{"quiet_preserves_JSON_errors_and_program_output",true},
    {"help_text_maximum_bytes",16384},{"help_JSON_maximum_bytes",32768},
    {"completion_JSON_maximum_bytes",16384},{"completion_maximum_words",128},
    {"completion_word_maximum_bytes",4096},{"filesystem_completion","delegated to shell"},
    {"shell_profiles_modified",false},{"value_combination_validation","existing command handlers"}};
}
}
