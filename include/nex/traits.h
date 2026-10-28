#pragma once
#include "nex/constructor_types.h"
namespace nex {
const Trait &traitDefinition(const Program &,const std::string &,Span={});
KindContext programKinds(const Program &);
Type constructorPattern(const Program &,Type);
unsigned argumentKind(const Program &,const Type &,Span={});
void prepareTraits(Program &);
void checkImplementations(Program &);
bool hasTraitWitness(const Program &,const Type &,const std::string &);
struct TraitWitness {const Implementation *implementation;TypeSubstitution arguments;};
std::optional<TraitWitness> selectedTraitWitness(const Program &,const Type &,const std::string &,Span={});
Type resolveProjection(Program &,Type,Span,unsigned);
Function &instantiateTraitMethod(Program &,const Function &,const std::vector<Type> &,Span);
std::string selectedImplementation(const Program &,const Type &,const std::string &,Span={});
}
