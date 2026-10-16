#pragma once
namespace nexrt {
inline constexpr const char *authenticationSchema=R"({"schema":"nex.wire/1","root":{"record":"Auth"},"records":{"Auth":[{"name":"schema","type":"str"},{"name":"tokens","type":{"list":{"record":"Token"}}}],"Token":[{"name":"user","type":"str"},{"name":"sha256","type":"str"}]}})";
}
