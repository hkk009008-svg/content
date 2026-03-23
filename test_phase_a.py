import phase_a_generator
import phase_e_learning

# mock out fetching
phase_e_learning.get_top_performing_context = lambda: "MOCKED CONTEXT"
phase_e_learning.fetch_live_youtube_trends = lambda: "MOCKED TRENDS"

ctx = {"topic": "How McDonald's actually makes its money from real estate, not selling burgers."}
phase_a_generator.generate_shorts_script(ctx)

import json
print(json.dumps(ctx["script_data"], indent=2))
