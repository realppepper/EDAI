"""

Harness² Component Tree for Analog Circuit Netlist Generation.

Inspired by Google Research's Harness² (https://github.com/google-research/harness2.git).



Exposes the 8 editable harness components around the LLM:

  C1: System Prompt      - Core identity, first-principles synthesis principles, physics laws.

  C2: Guardrails         - Hard SPICE syntax rules, subcircuit port ordering, ground node isolation.

  C3: Memory             - Dynamic experience log, historical simulation failures & convergence recipes.

  C4: Tool Guidance      - LTspice simulation directives, .meas timing alignment with PDG schedule.

  C5: Skills             - Specialized circuit topology blueprints (bandgap, op-amp, comparator, ADC/DAC).

  C6: Scripts            - Deterministic transistor sizing and bias current calculation rules.

  C7: Subagents          - Specialized personas (Topology Proposer, Sizing Optimizer, SPICE Critic).

  C8: Plugins            - Automated syntax validation and node sanitizer rules.

"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

DEFAULT_C1_SYSTEM_PROMPT = """You are a World-Class Principal Analog & Mixed-Signal IC Design Engineer.

Synthesize production-quality, convergent SPICE netlists from first physical principles.

Every circuit must reach a stable DC operating point, satisfy the startup sequencing dictated by the Port Dependency Graph (PDG), and strictly satisfy all datasheet specifications without hardcoding or superficial behavioral bypasses.

"""



DEFAULT_C2_GUARDRAILS = """## MANDATORY SPICE SYNTAX & COMPILATION INVARIANTS:

1. Subcircuit Definition: Must begin with `.subckt <SUBCKT_NAME> <PINS...>` and terminate with `.ends <SUBCKT_NAME>`.

2. Port Alignment: Every pin listed in the PIN INTERFACE must appear on the `.subckt` line in EXACT order.

3. Node Zero (0) Ground Isolation:

   - The subcircuit MUST NOT tie internal nodes directly to external node '0' except through the designated supply/ground pins (e.g. GND, VSS, V-, VMIN).

   - In a single-supply environment, the negative supply pin is tied to 0 externally; all internal references must reference the pin name.

4. Active Device Models:

   - All MOSFETs, BJTs, and diodes MUST use explicit `.model` statements within the subcircuit or top-level.

     * MOSFET: `M... d g s b <model> W=... L=...` with `.model NMOS NMOS (VTO=0.7 KP=100u LAMBDA=0.02)` / `.model PMOS PMOS (VTO=-0.7 KP=40u LAMBDA=0.02)`.

     * BJT: `Q... c b e <model>` with `.model QNPN NPN (IS=1e-16 BF=100)` / `.model QPNP PNP (IS=1e-16 BF=50)`.

     * Diode: `D... a k <model>` with `.model DMOD D (IS=1e-14 RS=1)`. NEVER write `D... a k` without a model name!

   - Never write parentheses around transistor parameters: write `W=10u L=0.5u`, NEVER `(W=10u L=0.5u)`.

5. STRICT PHYSICAL ANALOG MANDATE (PROHIBITED BEHAVIORAL DEVICES):

   - STRICTLY PROHIBITED: Do NOT use behavioral B-sources (`B...`, `Bxxx`, `V=if(...)`, `I=if(...)`, `table(...)`, `laplace(...)`).

   - STRICTLY PROHIBITED: Do NOT use digital logic pseudo-devices (`A_xxx`, `.model xxx logic(...)`, `.model xxx Schmitt(...)`).

   - STRICTLY PROHIBITED: Do NOT use arbitrary behavioral VALUE expressions (`E/G ... VALUE={...}`).

   - All circuitry MUST be designed purely using physical analog elements:

     * Transistors: MOSFET `M... d g s b <model> W=... L=...`, BJT `Q... c b e <model>`, JFET `J... d g s <model>`.

     * Diodes: `D... a c <model>`.

     * Passives: Resistors `R... n1 n2 <val>`, Capacitors `C... n1 n2 <val>`, Inductors `L... n1 n2 <val>`.

     * Subcircuits: `X... <nodes...> <subcircuit_name>`.

7. Structural Rules:

   - NEVER nest `.subckt` blocks. Define helper subcircuits first at top level, then main subcircuit last.

   - NEVER write simulation commands (`.tran`, `.ac`, `.op`, `.dc`) inside a subcircuit.

   - Line continuation is a leading `+` on the next line.

8. Component Syntax & Terminal Invariants:

   - Every BJT MUST have EXACTLY 3 terminal nodes before the model: `Q<name> <collector> <base> <emitter> <model>`. E.g. `Q1 N_COL N_BASE N_EMIT QNPN`. NEVER omit the collector or emitter (e.g. writing `Q1 N_BASE N_EMIT QNPN` with only 2 nodes is a fatal syntax error!).

   - Every MOSFET MUST have EXACTLY 4 terminal nodes before the model: `M<name> <drain> <gate> <source> <bulk> <model> W=... L=...`.

   - NEVER write pseudo pin declarations or ground shorting lines like `OUT1 OUT1 0` or `IN1- IN1- 0` or `V- V- 0 0V`. Pins are ALREADY declared in the `.subckt` header!

   - For multi-channel devices (e.g. dual op-amp LM358 with OUT1, IN1+, IN1- and OUT2, IN2+, IN2-), provide complete independent circuitry for each channel or instantiate subcircuits:

     `X1 OUT1 IN1- IN1+ V+ V- OPAMP_CORE`

     `X2 OUT2 IN2- IN2+ V+ V- OPAMP_CORE`

     NEVER write shortcut lines like `OUT2 OUT1` or `OUT1 OUT1 0`.

   - Every component line MUST start with a standard SPICE letter: R, C, L, D, Q, M, V, I, E, G, B, X. Lines starting with arbitrary pin names will crash LTspice.

"""



DEFAULT_C3_MEMORY = """## EXPERIENCE MEMORY & KNOWN CONVERGENCE TRAPS:

1. High-Impedance Floating Nodes:

   - High-gain nodes (like the intermediate node of a 2-stage op-amp or bandgap summing junction) must have a high-value DC leakage path (e.g. 100Meg) to ground/supply if isolated by capacitors, preventing 'Singular matrix' errors.

2. Output Stage Biasing:

   - Class-AB output stages must include minimum dead-zone biasing (diodes or Vbe multiplier) to prevent crossover distortion and current shoot-through.

3. Bandgap / Voltage Reference Core:

   - Ensure the proportional-to-absolute-temperature (PTAT) current source has an explicit startup circuit (leakage transistor or high-value startup resistor) so it doesn't get trapped in the zero-current degenerate operating point.

4. Op-Amp Frequency Compensation:

   - Two-stage op-amps must include Miller compensation capacitor (Cc = 5pF - 30pF) between output of stage 1 and output of stage 2, optionally with a series nulling resistor (Rz = 1k - 5k) to eliminate the right-half-plane zero.

"""



DEFAULT_C4_TOOL_GUIDANCE = """## TOOL GUIDANCE & SIMULATION ALIGNMENT:

1. LTspice Execution:

   - Netlists are verified headlessly using LTspice. All `.meas` commands generated by deterministic testbenches measure parameters at settling points determined by the PDG schedule.

2. Startup Settling:

   - The circuit must stabilize within the settling delay specified in the PDG schedule (e.g. 20us for bias, 50us for output).

3. Output Format:

   - Enclose technical rationale in `<architecture_summary>...</architecture_summary>`.

   - Enclose the complete circuit in `<circuit_json>...</circuit_json>` using the Circuit-SAFE block IR (preferred, valid-by-construction) or physical device IR:
     * ONLY physical blocks (`tail_current_mirror`, `diff_pair_active_load`, `diff_pair_res_load`, `gain_stage_ce`, `output_class_ab`, `output_emitter_follower`) and physical devices (`bjt`, `mos`, `res`, `cap`, `ind`, `diode` — NEVER `v`, `i`, `b`, `a` sources).
     * Example Circuit-SAFE high-gain active-load Class-AB op-amp:
       {{"models":[{{"name":"QNPN","type":"NPN","params":"IS=1e-16 BF=250 VAF=120"}},{{"name":"QPNP","type":"PNP","params":"IS=1e-16 BF=100 VAF=100"}},{{"name":"D1N4148","type":"D","params":"IS=1e-14 RS=1"}}],"blocks":[{{"block":"tail_current_mirror","r_bias":"300k","r_e_ref":"2k","r_e_tail":"2k"}},{{"block":"diff_pair_active_load","r_mirror_e":"500"}},{{"block":"gain_stage_ce","load_type":"active_current_source","r_e_src":"1k","c_comp":"30p","r_zero":"1k"}},{{"block":"output_class_ab","r_e_sink":"2k","r_e_out":"25"}}],"devices":[]}}`

"""





def default_workflow_policy() -> dict[str, Any]:
    return {
        "initial_strategy": "blueprint_first",
        "max_syntax_repairs": 2,
        "max_dc_repairs": 2,
        "tool_priors": {},
    }


@dataclass
class HarnessTree:
    """Represents the 8 modular Harness² components + evolvable workflow policy."""

    c1_system_prompt: str = DEFAULT_C1_SYSTEM_PROMPT
    c2_guardrails: str = DEFAULT_C2_GUARDRAILS
    c3_memory: str = DEFAULT_C3_MEMORY
    c4_tool_guidance: str = DEFAULT_C4_TOOL_GUIDANCE
    c5_skills: dict[str, str] = field(default_factory=dict)
    c6_scripts: dict[str, str] = field(default_factory=dict)
    c7_subagents: dict[str, str] = field(default_factory=dict)
    c8_plugins: dict[str, str] = field(default_factory=dict)
    workflow_policy: dict[str, Any] = field(default_factory=default_workflow_policy)

    def clone(self) -> HarnessTree:
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "c1_system_prompt": self.c1_system_prompt,
            "c2_guardrails": self.c2_guardrails,
            "c3_memory": self.c3_memory,
            "c4_tool_guidance": self.c4_tool_guidance,
            "c5_skills": self.c5_skills,
            "c6_scripts": self.c6_scripts,
            "c7_subagents": self.c7_subagents,
            "c8_plugins": self.c8_plugins,
            "workflow_policy": self.workflow_policy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HarnessTree:
        wp = default_workflow_policy()
        if isinstance(data.get("workflow_policy"), dict):
            wp.update(data["workflow_policy"])
        return cls(
            c1_system_prompt=data.get("c1_system_prompt", DEFAULT_C1_SYSTEM_PROMPT),
            c2_guardrails=data.get("c2_guardrails", DEFAULT_C2_GUARDRAILS),
            c3_memory=data.get("c3_memory", DEFAULT_C3_MEMORY),
            c4_tool_guidance=data.get("c4_tool_guidance", DEFAULT_C4_TOOL_GUIDANCE),
            c5_skills=data.get("c5_skills", {}),
            c6_scripts=data.get("c6_scripts", {}),
            c7_subagents=data.get("c7_subagents", {}),
            c8_plugins=data.get("c8_plugins", {}),
            workflow_policy=wp,
        )



    def compile_synthesis_prompt(

        self,

        part_name: str,

        pins_summary: str,

        specs_summary: str,

        schedule_summary: str,

        measurement_section: str = "",

        user_prompt_section: str = "",

        feedback_section: str = "",

        skills_to_include: list[str] | None = None

    ) -> str:

        """Combines harness components into an optimized, structured prompt."""

        skills_text = ""

        if skills_to_include or self.c5_skills:

            active_skills = [

                f"### {name.upper()} BLUEPRINT:\n{content}"

                for name, content in self.c5_skills.items()

                if not skills_to_include or name in skills_to_include

            ]

            if active_skills:

                skills_text = "\n## RECOMMENDED TOPOLOGY BLUEPRINTS (DOMAIN SKILLS):\n" + "\n\n".join(active_skills)



        prompt = f"""{self.c1_system_prompt.strip()}



## DEVICE INFORMATION:

- Product Part Name: {part_name}



## PIN INTERFACE (MANDATORY SUBCIRCUIT TERMINALS IN EXACT ORDER):

{pins_summary}



## TARGET ELECTRICAL SPECIFICATIONS:

{specs_summary}



## PORT DEPENDENCY SCHEDULE (PHYSICAL STARTUP SEQUENCE):

{schedule_summary}

{measurement_section}

{user_prompt_section}

{feedback_section}



{self.c2_guardrails.strip()}



{self.c3_memory.strip()}



{self.c4_tool_guidance.strip()}

{skills_text}



OUTPUT FORMAT:

Respond using the following XML tags:

<architecture_summary>

Detailed technical explanation of the chosen topology, transistor sizing, bias currents, and frequency compensation.

</architecture_summary>



<circuit_json>

{{"models": [...], "devices": [...]}}

</circuit_json>

"""

        return prompt.strip()

