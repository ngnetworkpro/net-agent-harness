from dataclasses import dataclass, field

@dataclass
class TermEntry:
    name: str
    definition: str

@dataclass
class IntentSpec:
    name: str
    description: str
    required_fields: list[str] = field(default_factory=list)

@dataclass
class FewShotExample:
    user: str
    normalized_intent: str
    extra: dict = field(default_factory=dict)

@dataclass
class DomainContext:
    domain: str
    description: str
    terms: list[TermEntry]
    intents: list[IntentSpec]
    examples: list[FewShotExample]

    def render_prompt_block(self) -> str:
        """Serialize the domain context into a system prompt section."""
        lines = [
            f"--- DOMAIN CONTEXT: {self.domain.upper()} ---",
            self.description,
            "",
            "## Glossary",
        ]
        
        for term in self.terms:
            lines.append(f"- **{term.name}**: {term.definition}")
            
        if self.intents:
            lines.extend(["", "## Supported Intents"])
            for intent in self.intents:
                reqs = ", ".join(intent.required_fields) if intent.required_fields else "None"
                lines.append(f"- **{intent.name}**: {intent.description} (Requires: {reqs})")
                
        if self.examples:
            lines.extend(["", "## Examples"])
            for ex in self.examples:
                lines.append(f"- User: \"{ex.user}\"")
                lines.append(f"  -> intent: {ex.normalized_intent}")
                for k, v in ex.extra.items():
                    lines.append(f"  -> {k}: {v}")
                    
        lines.append("--------------------------------------")
        return "\n".join(lines)
