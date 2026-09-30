"""Rule-regression tools for virtual-student consistency.

These metrics are **not** an independent oracle. They deliberately import the
production rules (`app.services.virtual_student.semantic`,
`app.services.virtual_student.state_rules`) so that the numbers track the
behaviour the application actually ships. A defect shared by the production
rules and these metrics is therefore invisible to this framework, because both
sides move together.

Read the results as a regression check on the production rules, not as
independent evidence that the virtual student is pedagogically correct. The
boundary and language-naturalness metrics are the only parts with their own
vocabulary; everything derived from student evidence reuses production output.
"""
