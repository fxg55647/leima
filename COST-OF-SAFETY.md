# The Cost of Safety? — A Four-Field Framework for AI Agent Ethics

## 1. The Bridge That Must Not Fall — and What That Costs

Engineering education carries a principle that is entirely correct: not even one bridge in a hundred should collapse. For bridges, this makes sense. Failure is physical and visible, the worst case is known in advance, and construction is a one-time investment whose safety margin can be calculated.

The principle is so obvious for bridges that it travels easily elsewhere. And that is where the problem lies — because it conceals the moral choice it is actually making.

Construction budgets are always finite. Every euro spent on over-engineering a bridge is taken from hospitals, schools, or other bridges. Zero tolerance in one place is not a neutral choice — it is an implicit decision to accept greater risk elsewhere. Perfect safety in one place costs safety somewhere else.

And what do we answer when the probability shrinks? One bridge in a hundred is easy to condemn. What about one in ten thousand? What about one in ten million — if removing that budget would let you build ten new bridges where none exist yet? The question does not become less uncomfortable as the numbers fall. It becomes harder.

This tension does not disappear in the age of AI. It multiplies.

In the world of bridges, risks are known and physical. The worst case is understood in advance. Cost scales linearly with safety. A bridge does not learn, adapt, or act autonomously.

In the world of AI agents, these assumptions break down. Failure is often invisible for a long time. The worst case is unknown and shifting. An attacker adapts to defenses in real time. An agent acts autonomously in situations its designer could not anticipate. Zero tolerance for an unknown and changing set of risks is not a cautious goal — it is an impossibility.

But the problem is not only technical. It is also moral.

AI technology that is never deployed out of fear is not a safe choice. It is an invisible moral cost — for everyone the technology could have helped. A developer who delays a useful application because it is not perfectly secure makes a moral choice just as much as a developer who ships an imperfect version. Neither escapes moral responsibility simply by acting or by not acting.

This is not a hypothetical question. When the Kenyan mobile payment system M-Pesa launched in 2007, it was imperfect — there were security gaps, regulation was unclear, and the risk of misuse was real. It launched anyway. Early research showed it had lifted hundreds of thousands of households out of extreme poverty and enabled women to move from subsistence farming into business — and this was before the user numbers truly exploded. If the developers had waited for perfect security, those people would have waited with them. Not deploying a technology is not a neutral state. It is a decision to preserve the current suffering unchanged.

This raises the question this essay tries to frame: if perfect safety is not a goal but a cost, what should we optimise for instead?

To sketch an answer, we need two separate axes. The first is economic: what is the expected return relative to the worst realistic harm? The second is moral: is the action itself justifiable regardless of its economic outcome? These axes form a four-field matrix that does not resolve ethical questions — but forces them to be asked correctly.

## 2. The First Field — Return Against Worst Realistic Harm

The answer begins with a simple observation: risk is not a single number but the product of two variables. Probability multiplied by severity. This is familiar from engineering — but with AI agents it forces a distinction that is rarely made aloud.

Optimal insecurity does not mean carelessness. It means that the safety investment must be proportioned to what can realistically happen — not to the worst imaginable scenario, but to the worst realistic one.

The difference matters. An agent sending calendar reminders can certainly go wrong. The worst realistic harm is a wrong time or a cancelled meeting — annoying but recoverable. An agent doing financial auditing might, if it fails, miss a significant discrepancy. The worst realistic harm is of a different order entirely.

This leads to the first practical principle: safety level should be function-specific, not system-wide. The same agent may require tight oversight in one function and loose oversight in another.

Probability changes the calculation dramatically. A failure rate of 1 in 100 is easy to condemn — it means every hundredth use ends in harm. But what about 1 in 10,000,000? If a technology helps a million people daily and a failure occurs once in ten years, the calculation shifts. It does not disappear — but it shifts.

Here lies a danger that must be recognised. Probability calculus tempts us to dissolve the quality of a harm behind its quantity. Low probability does not make harm acceptable if it is irreversible, falls on a vulnerable person, or violates something whose value cannot be measured in money. This is why the first field alone is not enough.

Reversibility is one of the most important variables that economic calculation does not automatically capture. A wrong calendar entry is reversible — it gets fixed. Leaked patient data is effectively permanent — it cannot be taken back. This means that for agents, the question is not only "can an error occur" but "can it be recovered from." Irreversible actions belong in a different category from reversible ones regardless of how small their probability is.


## 3. The Second Field — The Morality of the Action

Economic risk is measurable. The moral axis is harder — but no less real.

The moral axis asks: is the action justifiable regardless of what it produces? This is a different question from the economic one. The economic field looks at consequences — what happens and how likely. The moral axis looks at the nature of the action — who benefits, who is harmed, and what the actor's true motive is.

Consider an example. Two developers make the same technical decision: they ship an application whose security is not perfect. The first developer knows the application could lift millions out of poverty — they have seen M-Pesa's effects and believe they are doing the same. The second developer is chasing growth and investor money, and security is simply a cost item slowing down the schedule.

The technical decision is identical. The moral weight is not.

This observation matters because it prevents two common mistakes. The first is to condemn all imperfect technology equally regardless of what it aims to achieve. The second is to let good intentions launder all technical negligence — as though noble goals removed responsibility for consequences.

Motive does not erase harm. But it shapes how harm should be evaluated and who bears responsibility for fixing it.

The moral field is not a simple scale from selfish to noble. It is two-dimensional in the same way as the economic field. One can ask: how widely does the harm spread, and how much is the actor willing to own the consequences when harm occurs? A developer who ships an imperfect application but monitors actively, fixes errors quickly, and keeps users informed is in a different moral position from a developer who ships and disappears.

This brings us back to the bridge analogy — but from the other direction. A bridge builder cannot disappear after the bridge is finished. They are responsible for what they build. The same responsibility applies to a software developer — and in the age of AI agents it is greater than ever, because the agent acts independently in situations no one fully anticipated.

## 4. Day and Night — Where Morality Is Clear

The moral axis invites relativism. If everything depends on context, motivation, and probabilities, can anything be clearly wrong? Can we say that some action crosses an acceptable line — or is the line always negotiable?

In philosophy this is called the sorites paradox. At what point does a heap of sand grains cease to be a heap? At what point does day become night? There is no precise boundary — but that does not mean the categories are meaningless. At noon there is no ambiguity. At midnight there is no ambiguity. Dusk is real, but it is a narrow band between two clear zones.

The same structure applies to morality.

We can debate whether a particular security gap is acceptable given a technology's benefits. We can argue about where a failure probability becomes small enough. These are genuine and difficult questions. But there are also things that require no debate — if one stops to think for a moment.

Start with the easy case. A developer sells their users' patient data to a blackmailer in order to enrich themselves. Practically everyone considers this condemnable — the motive is transparently selfish and the victims pay the price.

But what if the motive changes? The developer sells the same data to the same blackmailer — but donates the proceeds entirely to building hospitals. Probably nearly as many people condemn this too. The harm to individual patients is disproportionate and concrete. Trust in healthcare data protection erodes more broadly. Good intentions do not undo what was done to those people whose data was sold.

These are not culturally contingent edge cases. They are anchor points of moral reasoning — things on which almost all people agree when they pause to think for a moment. Anchor points do not resolve the grey area. But they set a floor below which no calculation can go.

This is the most practical consequence of the four-field framework. The high moral risk quadrant is not a pricing question — it is a categorical limit. A protocol, application, or agent that operates there does not need more detailed risk analysis. It needs refusal.


## 5. The Interaction of the Fields — Where the Logic Holds and Where It Breaks

Two fields together make four quadrants. Three of them are fairly clear. One is treacherous.

High economic risk and high moral risk is the obvious case — do not proceed. Low economic risk and low moral risk is also clear — you can operate with looser safety, the harm is small and recoverable. High economic risk and low moral risk is insurable — this is an engineer's problem, not a philosopher's.

The treacherous quadrant is low economic risk and high moral risk.

It is treacherous because the market mechanism does not correct it. If the harm is economically small, a company has no financial incentive to avoid it. But the moral harm can still be large — a third party wronged, privacy violated, trust destroyed. This is precisely the quadrant where free markets fail systematically and where some other mechanism — transparency, reputation, regulation, or a protocol-level prohibition — is the only remedy.

There is also a dynamic tension between the fields that a static matrix does not fully capture. The same function can shift from one quadrant to another as context changes. An agent sending calendar reminders sits in the low-risk quadrant — until it starts handling appointment data from a clinic. An agent doing bookkeeping is reasonably safe — until it gains access to customers' personal information. The quadrant is not a property of the function. It is a property of the function combined with its context.

Here lies one practical danger that is hard to guard against: gradual drift. No developer usually decides to step into the night all at once. Instead, the agent gains access to the calendar today, to medical appointments next week, to automatic prescription renewals next month. Each step feels small. The whole has shifted from one quadrant to another without anyone making a conscious decision. The job of the architecture is to force reassessment whenever a function takes one more step forward in the dusk.

This leads to a practical principle that is easier to state than to implement: safety decisions should be made function-by-function and context-sensitively, not once at the system level. The same agent may sit in different quadrants depending on what data it handles, on whose behalf it acts, and what the consequences of its errors might be.

The four-field framework does not resolve these questions. It is a structuring tool for the conversation — one that prevents economic logic from being smuggled in as a moral decision, or vice versa. The right decisions emerge from the deliberation that happens inside the framework. But without the framework, deliberation easily starts from the wrong question.


## 6. The Game Change No Expert Questioned

Everyone who has tried to take AI safety seriously — OpenAI, NIST, the international research community — has approached it with the same underlying assumption: there exists a set of risks, they can be identified, measured, and managed through process. Better data, better methods, more stakeholders at the table. This is a rational approach — and it works in a deterministic world.

OpenAI saw as early as 2019 that the human side is non-deterministic — in a published paper they argued that AI safety needs social scientists, because human values are inconsistent and context-dependent. The question that went unasked was a different one: who should decide in the first place which safety solution is morally acceptable — and is an engineer the right person to make that decision alone? A historian, a medical ethicist, or a community representative whose data is at stake sees the treacherous quadrant differently from the person building the system. NIST took the idea further in its 2023 AI Risk Management Framework — explicitly acknowledging that AI risks are sociotechnical, not purely technical. Yoshua Bengio assembled that in February 2026 into an international report of over a hundred experts from thirty countries. Every step was in the right direction.

But none of them questioned that underlying assumption — that the model itself is a deterministic system whose risks are manageable through process.

An LLM is not a deterministic system with identifiable faults. It is a statistical system in which the same input can produce different outputs on different occasions, in which "error" is not a deviation from normal operation but normal operation in certain situations, and in which no one — not even the builder — fully understands why it does what it does. You cannot map the risks of a system whose behaviour is fundamentally statistical and context-dependent. You cannot measure reliability the way you measure the load-bearing capacity of a bridge. You cannot fix a problem with a patch when the problem is not a bug in the code but a feature of how the model operates.

Before LLMs, security either worked or it did not. A regex detected an attack or it did not. A firewall let something through or it blocked it. These are binary states — and in a binary world, perfection is at least theoretically achievable. The next update can fix everything. This intuition has survived even as the world changed.

With LLMs, security became statistical. There is no state in which the system "works correctly" in all cases — there are only probabilities, contexts, and boundary conditions. This is not a temporary problem that will be solved in the next version. It is a fundamental property of what these systems are. The expected update that will fix everything is not late. It is not coming.

Here also lies why the security community has been so quiet. A solution whose approach cannot in principle ever reach one hundred percent is a different design philosophy from what we are used to — even if it fixes 95%. It can feel like a betrayal, even a surrender. Like a public admission that this is as far as it goes. But no one has any idea what a perfect solution would even look like. Perhaps it exists. But if no one can point the way there, waiting is not caution — it is hiding behind a hypothetical. The best available is better than a perfection no one knows how to build.


## 7. Practice — The Four-Field Framework in Building AI Agents

Theory is only useful if it changes how things are done. How does the four-field framework show up in practice when building AI agents?

Today's autonomous agents — such as the open-source OpenClaw, which reached over 100,000 GitHub stars in its first week in 2026 — can send email, manage calendars, execute commands, and browse the web on a user's behalf. They represent in practice the first generation of technology in which these questions arise in everyday software development.

OpenClaw's adoption speed also revealed something the security community was reluctant to admit: when the reward sounds attractive enough, people are willing to throw security out entirely. Developers installed OpenClaw with full system privileges, unaudited code, and no sandbox — not because they were careless, but because waiting for a perfect version felt the same as waiting for something that would never come. This is a predictable consequence of a culture that treats security as a binary state rather than a continuum. When the bar is set at perfect, and perfect is unachievable, the real choice is often zero. Relative safety — genuine but bounded — is the only standard that has practical influence on human behaviour.

The framework points toward three practical principles.

First: safety level is function-specific. An agent sending calendar reminders and an agent handling patient records do not belong in the same safety category even if they run on the same platform. One level of safety for all functions is simultaneously over-engineering in one place and under-engineering in another.

The same logic applies at the industry level. A car repair shop that uses an agent to handle bookings, parts orders, and service reminders operates in low moral risk: if the agent orders the wrong parts or double-books an appointment, the harm falls mostly on the shop itself. The threshold for adopting such an agent is low, and the benefits — freed staff time, fewer missed follow-ups, faster procurement — are attainable even for a small operator without significant security investment.

A bank or hospital running agents on the same platform faces a fundamentally different moral calculation — despite the technical similarity. When an agent handles a customer's financial data or participates in clinical decisions, third-party exposure is unavoidable. Errors are not just costly — they can be irreversible, and they fall on people who did not themselves choose to bear this risk. Both the bank and the hospital can benefit enormously from agents. But both must weigh the moral side in a way the car shop barely needs to.

Second: minimising personal data is a market mechanism for implementing ethics. If an agent can only access the data it strictly needs to complete its task, the moral risk quadrant shrinks automatically. This does not require regulation — it requires an architectural decision.

Third: irreversible actions require their own confirmation logic. An agent that sends an email, deletes a file, or makes a financial commitment operates differently from an agent that reads a calendar. Irreversibility automatically raises both the economic and moral risk by an order of magnitude.

These principles do not resolve every question. They do not say exactly where the line of acceptable risk runs. But they prevent the worst — the situation where economic urgency or technical convenience makes the moral decision on the developer's behalf, without anyone noticing.

For the practical applications of optimal insecurity — including decentralised insurance protocols for managing agent risk — see [Insuring the Agent](INSURANCE-FOR-AGENTS.md).


## 8. Conclusion — What Optimal Insecurity Actually Means

Optimal insecurity is a bad name. It sounds like a defence of irresponsibility — which is precisely why it appears in the title with a question mark. A better name might be proportional safety, or perhaps simply responsible risk. But the name matters less than the idea behind it.

It is honesty about what safety costs — and who pays. Perfect safety is not free. It costs development time, deployment speed, and ultimately the benefit that a technology never delivers to those who would need it most. M-Pesa was imperfect. It still changed the lives of millions by giving them access to modern payment services for the first time.

The four-field framework is not a moral algorithm. It does not give answers — it forces the right questions to be asked separately. What is the real economic risk, not the imagined worst case? Is the action morally justifiable regardless of what it produces? These questions lead somewhere different from a single vague safety question answered by intuition or fear.

Anchor points still exist. The grey area can be negotiated. But there is also clear night — actions that cannot be justified by any calculation. A developer who knows where night begins and steps there anyway has not optimised insecurity. They have simply chosen wrong.

Engineering education taught us that bridges must not fall. That was right for bridges. The age of AI agents demands more precise thinking — not looser morality, but sharper. Optimal insecurity is precision, not indifference.

There is one final irony worth naming. The pursuit of perfect safety has not made us safer — it has made us dishonest. Dishonest about what safety costs, dishonest about who pays when we delay, and dishonest about what people actually do when the bar is set impossibly high. They do not wait. They route around it.

Honesty about the limits of safety is not a concession to risk. It is the only foundation on which real safety standards can be built and maintained. When we stop pretending that perfect is achievable, we can start building something that is genuinely good — and demanding it of each other. That is what frees us: not the illusion of zero risk, but the clarity to see what risk we are actually taking, why, and on whose behalf.
