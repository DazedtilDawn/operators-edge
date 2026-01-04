# Research Request: Direct LLM API Integration for Operator's Edge

## Project Context

**Objective:** Enable Operator's Edge to call external LLM APIs directly for research tasks, eliminating manual copy-paste workflow.

**Current State:** The system generates research prompts via `/edge-research` but requires users to:
1. Copy the generated prompt
2. Paste into external tool (Perplexity, Gemini Deep Research, etc.)
3. Wait for response
4. Copy results back
5. Run `/edge-research-results` to process

**Constraints:**
- Must work offline/degraded if APIs unavailable
- API keys must be securely stored (not in YAML state)
- Cost tracking is important (API calls have real costs)
- Should support multiple providers (not lock-in to one)

## Why This Research Is Needed

The manual research handoff breaks the autonomous loop. When Scout finds a task requiring research, dispatch must stop and wait for human intervention. Direct API integration would enable:
- Fully autonomous research → plan → execute cycles
- Faster iteration (no human in the loop for simple research)
- Cost-aware decisions (system knows research cost vs value)

## Questions to Answer

### 1. Architecture Patterns

1. What are the recommended patterns for multi-provider LLM integration in Python?
   - Adapter pattern per provider?
   - Unified interface libraries (LiteLLM, LangChain)?
   - Direct SDK usage vs abstraction layers?

2. How should provider selection work?
   - User preference?
   - Task-based routing (simple → cheap model, complex → expensive)?
   - Automatic fallback chains?

3. What's the best practice for async vs sync API calls in agent frameworks?

### 2. Provider Capabilities

1. Which providers offer "deep research" capabilities (web search + synthesis)?
   - Perplexity API
   - Google Gemini with grounding
   - OpenAI with web browsing
   - Anthropic Claude (with tools)

2. What are the rate limits and pricing for each?
   - Requests per minute
   - Tokens per request
   - Cost per 1K tokens (input/output)

3. Which providers support structured output (JSON mode)?

### 3. Security & Configuration

1. How should API keys be stored and managed?
   - Environment variables?
   - Encrypted config file?
   - OS keychain integration?
   - `.env` file with gitignore?

2. What's the recommended pattern for key rotation?

3. How to handle API key validation at startup vs lazy validation?

### 4. Cost Management

1. How should the system track and report API costs?
   - Per-session tracking?
   - Budget limits with alerts?
   - Cost-per-objective attribution?

2. What's a reasonable cost ceiling for autonomous research?
   - Per-query limit?
   - Daily/weekly budget?

3. How to estimate cost before making a call?

### 5. Error Handling & Resilience

1. How to handle transient failures (rate limits, timeouts)?
   - Exponential backoff?
   - Circuit breaker pattern?

2. How to gracefully degrade when APIs are unavailable?
   - Fall back to prompt generation (current behavior)?
   - Cache recent results?

3. How to handle partial responses or truncated output?

### 6. Response Processing

1. How to validate research results before using them?
   - Confidence scoring?
   - Source verification?
   - Hallucination detection?

2. How to extract actionable insights from free-form research text?
   - Structured prompts requesting specific format?
   - Post-processing extraction?

3. How to handle conflicting information from multiple sources?

## Requested Output Format

Please provide:

1. **Recommendation**: Your suggested architecture approach (1-2 sentences)

2. **Provider Comparison Table**:
   | Provider | Deep Research | Cost/1K tokens | Rate Limit | Structured Output |
   |----------|---------------|----------------|------------|-------------------|
   | ... | ... | ... | ... | ... |

3. **Implementation Approach**: Specific next steps to implement (5-7 bullets)
   - Which library/SDK to use
   - Configuration structure
   - Key integration points with existing code

4. **Warnings**: Things to watch out for (3-5 bullets)
   - Common pitfalls
   - Cost surprises
   - Security gotchas

5. **Code Skeleton**: Example Python structure for the integration
   ```python
   # Suggested class/function signatures
   ```

## Integration Points in Current Codebase

The research system lives in:
- `research_utils.py` - Research prompt generation and state management
- `edge_config.py` - Configuration constants

Key functions to extend:
- `generate_research_prompt()` - Currently returns string; could call API
- `add_research_results()` - Currently manual; could auto-populate
- `create_research_item()` - Could add API response metadata

## Success Criteria

A successful implementation would:
1. Support at least 2 LLM providers (Perplexity + one other)
2. Track costs per research call
3. Fall back gracefully to prompt-only mode
4. Integrate with existing `/edge-research` and `/edge-research-results` commands
5. Store API keys securely (not in git)
6. Add no more than 2 new dependencies
