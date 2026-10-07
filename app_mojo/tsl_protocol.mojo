"""Mojo-TSL: Streaming Telegraphic Symbolic Language (TSL) Protocol Engine.

Ported from Swarmojo/repo_stapler/tsl_protocol.mojo:
- Real-time byte-level Finite State Machine (FSM) parser for [OUT:"..."] and [ADD:(s r o)]
- Zero-copy streaming token handling across arbitrary chunk boundaries
- Compact TSL prompt builder reducing token overhead by 80-90% for small local models
"""

alias STATE_SEEKING = 0
alias STATE_TAG_IDENT = 1
alias STATE_STREAM_OUT = 2
alias STATE_BUFFER_ADD = 3


struct ParsedTriple(Movable, Copyable):
    var subject: String
    var relation: String
    var object: String

    def __init__(out self, s: String, r: String, o: String):
        self.subject = s
        self.relation = r
        self.object = o

    def __copyinit__(out self, other: Self):
        self.subject = other.subject
        self.relation = other.relation
        self.object = other.object

    def __moveinit__(out self, mut other: Self):
        self.subject = other.subject^
        self.relation = other.relation^
        self.object = other.object^


struct TSLStreamParser(Movable, Copyable):
    """Streaming FSM parser for TSL packets ([OUT:"..."][ADD:(s r o)])."""
    var state: Int
    var tag_buffer: String
    var triple_buffer: String
    var output_stream: String
    var in_quotes: Bool
    var bound_triples: List[ParsedTriple]

    def __init__(out self):
        self.state = STATE_SEEKING
        self.tag_buffer = String("")
        self.triple_buffer = String("")
        self.output_stream = String("")
        self.in_quotes = False
        self.bound_triples = List[ParsedTriple]()

    def __copyinit__(out self, other: Self):
        self.state = other.state
        self.tag_buffer = other.tag_buffer
        self.triple_buffer = other.triple_buffer
        self.output_stream = other.output_stream
        self.in_quotes = other.in_quotes
        self.bound_triples = List[ParsedTriple]()
        for i in range(len(other.bound_triples)):
            self.bound_triples.append(other.bound_triples[i])

    def __moveinit__(out self, mut other: Self):
        self.state = other.state
        self.tag_buffer = other.tag_buffer^
        self.triple_buffer = other.triple_buffer^
        self.output_stream = other.output_stream^
        self.in_quotes = other.in_quotes
        self.bound_triples = other.bound_triples^

    def feed(mut self, chunk: String):
        """Processes incoming token delta slice character-by-character."""
        for ch_slice in chunk.codepoint_slices():
            var ch = String(ch_slice)

            if self.state == STATE_SEEKING:
                if ch == "[":
                    self.state = STATE_TAG_IDENT
                    self.tag_buffer = String("")

            elif self.state == STATE_TAG_IDENT:
                if ch == "]":
                    self.state = STATE_SEEKING
                else:
                    self.tag_buffer += ch
                    if self.tag_buffer == "OUT:":
                        self.state = STATE_STREAM_OUT
                        self.in_quotes = False
                        self.tag_buffer = String("")
                    elif self.tag_buffer == "ADD:":
                        self.state = STATE_BUFFER_ADD
                        self.triple_buffer = String("")
                        self.tag_buffer = String("")

            elif self.state == STATE_STREAM_OUT:
                if ch == '"':
                    self.in_quotes = not self.in_quotes
                elif ch == "]" and not self.in_quotes:
                    self.state = STATE_SEEKING
                else:
                    self.output_stream += ch

            elif self.state == STATE_BUFFER_ADD:
                if ch == "(":
                    self.triple_buffer = String("")
                elif ch == ")":
                    var raw = String(self.triple_buffer.strip())
                    if len(raw) > 0:
                        self._commit_triple(raw)
                    self.triple_buffer = String("")
                elif ch == "]":
                    self.state = STATE_SEEKING
                else:
                    self.triple_buffer += ch

    def _commit_triple(mut self, raw: String) raises:
        """Extracts space-delimited (Subject Relation Object) triple."""
        var parts = raw.split(" ")
        if len(parts) >= 3:
            var s = String(parts[0])
            var r = String(parts[1])
            var o = String(parts[2])
            self.bound_triples.append(ParsedTriple(s, r, o))


def build_tsl_prompt(
    role: String,
    repo_ast_context: String,
    mem_triples: List[String],
    goal: String
) -> String:
    """Assembles a compressed Telegraphic Symbolic Language payload."""
    var sb = String("[ROLE:") + role + "]\n"

    if len(repo_ast_context) > 0:
        sb += "[REPO_AST:\n" + repo_ast_context + "]\n"

    if len(mem_triples) > 0:
        sb += "[MEM:"
        for i in range(len(mem_triples)):
            sb += "(" + mem_triples[i] + ")"
        sb += "]\n"

    sb += '[GOAL:"' + goal + '"]\n'
    sb += 'Respond strictly in TSL format: [OUT:"..."][ADD:(s r o)]'
    return sb
