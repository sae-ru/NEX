Original resource C-table prefix retained from NEX source155.

The header is byte-for-byte from runtime/nex_ffi.h at recovery commit
7b5f37c53d5533fec4bc24bd548bd27242887878. Its SHA256 is 5fb36a07bbe06e7a51dd94047ddfbfc55989760995234ea2718de13d5d368c3f.
It predates resource_create_with_parents; its resource prefix is296 bytes on
the supported64-bit ABI. Do not rewrite it when extending the live C table.
The dependent-resource source gate compiles real legacy producers with this
header and executes them through the new native and independent AST runtimes.
