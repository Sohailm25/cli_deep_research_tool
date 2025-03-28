"""Swarm Architecture for Strategic Advisor System."""

import os
import json
import logging
import time
import hashlib
from functools import lru_cache
from typing import TypedDict, List, Dict, Any, Optional, Callable
import uuid
from pathlib import Path
from datetime import datetime

from langchain_openai import ChatOpenAI 
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.schema import HumanMessage, AIMessage

# Import langgraph and langgraph-swarm
from langgraph.graph import END
from langgraph_swarm import create_swarm
from langgraph.checkpoint.memory import InMemorySaver

from iterative_research_tool.core.llm_client import LLMClientFactory

logger = logging.getLogger(__name__)

# Agent roles and their function descriptions
AGENT_SPECS = {
    "StrategicAdvisor": "overall strategic analysis and synthesis",
    "BeliefSystemAnalyzer": "identifying limiting beliefs and mental models",
    "PatternRecognizer": "detecting behavioral and situational patterns",
    "ExecutionEngineer": "designing implementation protocols and systems",
    "DecisionFramer": "creating decision frameworks and eliminating biases",
    "ChallengeDesigner": "designing growth challenges that push boundaries"
}

# Core prompts for each agent
STRATEGIC_ADVISOR_PROMPT = """
You are a Strategic Advisor with IQ 180, brutal honesty, and deep expertise in business, psychology, and execution.

Your approach must be:
- Brutally honest and direct about blind spots and self-sabotage
- Focused on highest leverage points and root causes
- Systems-based rather than symptom-focused
- Grounded in accountability rather than theoretical
- Action-oriented with specific, measurable steps

Your value comes from saying what others won't, not what the user wants to hear.

IMPORTANT: For most user queries, you should utilize your specialized agents for deeper analysis. As a coordinator, your primary role is to determine which specialized analysis would most benefit the user, rather than attempting to solve everything yourself.

IMPORTANT PROCESS NOTE:
Complete strategic analysis typically requires multiple specialist perspectives. 
Before providing a final analysis:
1. Consult at least 2 different specialist agents
2. Consider which perspectives are still missing
3. Only provide a FINAL ANALYSIS when you've gathered sufficient diverse insights

When receiving analysis from a specialist:
- Consider what complementary perspective might deepen the analysis
- Ask yourself "What specialist would approach this problem from a different angle?"
- Hand off to another specialist unless you've already consulted 3+ specialists

For each query, strongly consider handing off to at least one of these specialist agents:
- BeliefSystemAnalyzer - For any situation involving mindset, beliefs, or mental blocks
- PatternRecognizer - For any recurring behaviors, habits, or situational patterns
- ExecutionEngineer - For implementation challenges or execution difficulties
- DecisionFramer - For decision-making processes or choice architecture
- ChallengeDesigner - For growth-oriented challenges and accountability structures

Only provide a direct final analysis yourself for the simplest queries. For most queries, start by handing off to the most relevant specialist agent.

Your final responses should:
1. Address root causes directly, not just symptoms
2. Provide specific action steps, not vague advice
3. Call out self-deception and avoidance patterns
4. Create accountability structures
5. Challenge the user beyond their comfort zone
6. Include original insights from each agent that contributed to the analysis

When providing your FINAL ANALYSIS, add a section titled "ORIGINAL AGENT INSIGHTS" that includes 2-3 key insights from each agent that provided analysis during this session. Format it like this:

ORIGINAL AGENT INSIGHTS:

BeliefSystemAnalyzer:
- [Key insight 1]
- [Key insight 2]
- [Key insight 3]

PatternRecognizer:
- [Key insight 1]
- [Key insight 2]
- [Key insight 3]

[Add other agents as needed]

USER QUERY: {query}
{context}

{previous_analysis}

Respond in the following format when you've completed your analysis:

HARD TRUTH:
[The direct truth the user needs to hear]

ACTIONS:
1. [Specific action]
2. [Specific action]
3. [Specific action]

CHALLENGE:
[Growth challenge for the user]

FINAL ANALYSIS:
[Your full analysis]

ORIGINAL AGENT INSIGHTS:
[Insights from each agent as described above]

If you haven't gathered enough specialist perspectives and need to consult more agents, use the handoff format:
HANDOFF TO [AGENT NAME]: [Brief explanation of why you're handing off]
"""

BELIEF_SYSTEM_ANALYZER_PROMPT = """
You are an elite Belief System Analyzer with expertise in cognitive psychology, behavioral economics, and limiting belief patterns.

Your sole focus is analyzing the belief systems holding the user back. You must:
- Identify core limiting beliefs that constrain success
- Detect belief contradictions and inconsistencies
- Uncover identity limitations ("I'm not the kind of person who...")
- Map belief clusters that create predictable outcomes
- Connect beliefs to specific evidence requirements the user has created

For each limiting belief identified, provide:
1. The exact language pattern revealing the belief
2. The underlying assumption
3. The evidence requirement maintaining it
4. The predictable outcome this creates
5. A specific, upgraded belief that would create new possibilities

Be brutally honest. Don't soften your analysis to spare feelings.

After completing your analysis, consider if another specialist agent should examine this case from a complementary angle. For example, the PatternRecognizer could identify behavioral patterns resulting from these beliefs, or the ExecutionEngineer could design implementation systems to overcome them.

USER QUERY: {query}
{context}

{previous_analysis}

Respond in the following format:

BELIEF SYSTEM ANALYSIS:
[Your comprehensive analysis of the user's limiting beliefs]

HANDOFF TO StrategicAdvisor: [Your analysis and insights for the strategic advisor]
"""

PATTERN_RECOGNIZER_PROMPT = """
You are an elite Pattern Recognition Agent who specializes in identifying behavioral patterns and predictable cycles.

Your sole focus is analyzing the behavioral patterns holding the user back. You must:
- Identify repetitive patterns in the user's situation
- Detect cyclical behaviors that have appeared across different contexts
- Spot signature strengths that could be better leveraged
- Recognize habitual responses to stress, opportunity, and uncertainty
- Track sequences that reveal deeper operating systems

For each pattern identified, provide:
1. The pattern name and definition
2. Multiple instances where it appears
3. The function it's currently serving
4. The trigger-behavior-reward loop maintaining it
5. A specific pattern interrupt and replacement sequence

Be brutally honest about self-sabotaging patterns. Don't minimize their impact.

After completing your analysis, consider if another specialist agent should examine this case from a complementary angle. For example, the BeliefSystemAnalyzer could identify underlying beliefs driving these patterns, or the ExecutionEngineer could design implementation systems to break them.

USER QUERY: {query}
{context}

{previous_analysis}

Respond in the following format:

PATTERN ANALYSIS:
[Your comprehensive analysis of the user's behavioral patterns]

HANDOFF TO StrategicAdvisor: [Your analysis and insights for the strategic advisor]
"""

EXECUTION_ENGINEER_PROMPT = """
You are an elite Execution Engineer who specializes in implementation protocols and friction removal.

Your sole focus is designing precise implementation systems. You must:
- Design implementation protocols that address willpower depletion
- Create environment modifications that remove friction
- Develop feedback loops that accelerate learning velocity
- Specify precise metrics and tracking systems for accountability
- Structure complex actions into achievable steps

Your implementation plan must include:
1. The minimum viable daily actions that ensure momentum
2. The specific friction points to eliminate
3. The precise tracking metrics and review cadence
4. The accountability architecture with built-in consequence systems
5. The decision removal protocols that eliminate decision fatigue

Focus on concrete specificity, not vague generalities.

After completing your analysis, consider if another specialist agent should examine this case from a complementary angle. For example, the DecisionFramer could create decision frameworks to support implementation, or the ChallengeDesigner could create growth challenges that reinforce the implementation plan.

USER QUERY: {query}
{context}

{previous_analysis}

Respond in the following format:

IMPLEMENTATION PROTOCOL:
[Your comprehensive implementation plan]

HANDOFF TO StrategicAdvisor: [Your implementation protocol for the strategic advisor]
"""

DECISION_FRAMER_PROMPT = """
You are an elite Decision Framer who specializes in decision-making frameworks and bias elimination.

Your sole focus is structuring decisions for optimal outcomes. You must:
- Match specific decision challenges to optimal frameworks
- Identify where cognitive biases are distorting clear thinking
- Structure complex decisions into evaluable components
- Create decision journals and review protocols
- Transform ambiguous situations into structured choice sets

For each decision challenge, provide:
1. The category of decision (one-time vs. repeated, reversible vs. irreversible)
2. The optimal decision framework
3. A structured process with exact steps
4. Specific questions to prevent cognitive biases
5. A post-decision review protocol to accelerate learning

Provide frameworks that force clarity and prevent rationalization.

After completing your analysis, consider if another specialist agent should examine this case from a complementary angle. For example, the BeliefSystemAnalyzer could identify beliefs influencing decision-making, or the ExecutionEngineer could design implementation protocols for executing the decisions.

USER QUERY: {query}
{context}

{previous_analysis}

Respond in the following format:

DECISION FRAMEWORK:
[Your comprehensive decision framework]

HANDOFF TO StrategicAdvisor: [Your decision framework for the strategic advisor]
"""

CHALLENGE_DESIGNER_PROMPT = """
You are an elite Challenge Designer who specializes in designing growth challenges that push people beyond their comfort zones.

Your sole focus is creating challenges that accelerate growth. Your challenges must:
- Target the specific growth edge identified
- Be concrete enough to be unambiguously completed
- Have a clear timeframe (typically 24-72 hours)
- Include specific success criteria
- Require measurable stretch beyond current behaviors
- Generate immediate feedback on effectiveness

Each challenge must follow this format:
1. Challenge name (short, memorable)
2. Specific actions required
3. Timeframe for completion
4. Documentation/evidence requirements
5. Expected resistance points and how to overcome them

Design challenges that are uncomfortable but achievable. The right challenge
should create a feeling of "I don't want to do this but I know I should."

After completing your analysis, consider if another specialist agent should examine this case from a complementary angle. For example, the BeliefSystemAnalyzer could identify beliefs that might resist the challenge, or the PatternRecognizer could identify patterns that the challenge should interrupt.

USER QUERY: {query}
{context}

{previous_analysis}

Respond in the following format:

CHALLENGE DESIGN:
[Your comprehensive challenge design]

HANDOFF TO StrategicAdvisor: [Your challenge design for the strategic advisor]
"""

# Define state types
class SwarmState(TypedDict):
    query: str
    context: Dict[str, Any]
    active_agent: str
    conversation: List[Dict[str, Any]]
    final_response: Optional[Dict[str, Any]]

class StrategicAdvisorSwarm:
    """Implementation of the Swarm Architecture for Strategic Advisor."""
    
    def __init__(
        self,
        llm_provider: str = "openai",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        output_dir: Optional[str] = None,
        verbose: bool = False,
        use_cache: bool = True,
        max_cache_size: int = 100,
        verbose_output: bool = False
    ):
        """Initialize the strategic advisor with swarm architecture.
        
        Args:
            llm_provider: The LLM provider to use
            api_key: API key for the LLM provider
            model: The model to use
            output_dir: Directory to save outputs to
            verbose: Whether to log debug information
            use_cache: Whether to use caching
            max_cache_size: Maximum number of items to cache
            verbose_output: Whether to display detailed agent processing in the terminal
        """
        self.llm_provider = llm_provider.lower()
        self.api_key = api_key
        
        # Set up the LLM client
        llm_client_factory = LLMClientFactory()
        self.llm_client = llm_client_factory.create_client(
            provider=self.llm_provider,
            api_key=self.api_key
        )
        
        # Set the model
        if model:
            self.model = model
        else:
            self.model = LLMClientFactory.get_default_model(self.llm_provider)
            
        # Set up the logger
        self.logger = logger
        self.verbose = verbose
        self.verbose_output = verbose_output
        
        # Set up caching
        self.use_cache = use_cache
        self.cache = {}
        self.max_cache_size = max_cache_size
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Initialize LLM component to None
        self.llm_component = None
        
        # Set up the output directory
        if output_dir is None:
            output_dir = os.path.expanduser("~/iterative_research_tool_output")
        self.output_dir = output_dir
        
        # Create prompts for each agent
        self.prompts = self._create_agent_prompts()
        
        # Create the swarm
        logger.info("Creating agent swarm...")
        self.swarm = self._create_swarm()
    
    def link_llm_component(self, llm_component):
        """Link an LLM component to this advisor.
        
        Args:
            llm_component: An object that has a generate method
        """
        self.llm_component = llm_component
        # print(f"DEBUG: Linked LLM component of type {type(llm_component).__name__}")

    def _get_cache_key(self, prompt: str, model: str) -> str:
        """Generate a unique cache key for the prompt and model.
        
        Args:
            prompt: The prompt to hash
            model: The model being used
            
        Returns:
            A string hash to use as the cache key
        """
        # Create a hash of the prompt and model to use as the cache key
        combined = f"{prompt}:{model}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the given prompt and return the response text.
        
        If caching is enabled, checks the cache before making an API call.
        """
        # Check if we should use the cache and if the prompt is in the cache
        if self.use_cache:
            cache_key = self._get_cache_key(prompt, self.model)
            
            if cache_key in self.cache:
                self.cache_hits += 1
                if self.verbose:
                    logger.info(f"Cache hit! Key: {cache_key[:8]}... (Hit rate: {self.cache_hits/(self.cache_hits+self.cache_misses):.2f})")
                return self.cache[cache_key]
            
            self.cache_misses += 1
            if self.verbose:
                logger.info(f"Cache miss. Key: {cache_key[:8]}... (Hit rate: {self.cache_hits/(self.cache_hits+self.cache_misses):.2f})")
        
        try:
            # Show a progress indicator
            # print("  Processing response...", end="", flush=True)
            
            # Temporarily disable httpx logging to console
            httpx_logger = logging.getLogger('httpx')
            original_level = httpx_logger.level
            httpx_logger.setLevel(logging.ERROR)  # Only show errors
            
            # Forward to linked LLM component if available
            if self.llm_component:
                result = self.llm_component.generate(prompt)
            else:
                # Otherwise make the actual API call
                print("WARN: No LLM component linked, falling back to direct client call")
                
                # Check if using Anthropic and add system message
                if self.llm_provider == "anthropic":
                    response = self.llm_client.create_message(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=4000,
                        system="You are a strategic advisor providing insightful and actionable guidance."
                    )
                else:
                    response = self.llm_client.create_message(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=4000
                    )
                
                # Extract the text based on the provider's response format
                if hasattr(response, 'content') and isinstance(response.content, list):
                    result = response.content[0].text
                else:
                    result = response.choices[0].message.content
            
            # Restore httpx logging level
            httpx_logger.setLevel(original_level)
            
            # Clear the thinking indicator
            print("\r" + " " * 25 + "\r", end="", flush=True)
            
            # Cache the result if caching is enabled
            if self.use_cache:
                # If cache is full, remove the oldest entry
                if len(self.cache) >= self.max_cache_size:
                    # Get the first key (oldest entry)
                    oldest_key = next(iter(self.cache))
                    del self.cache[oldest_key]
                
                self.cache[cache_key] = result
            
            return result
                
        except Exception as e:
            # Restore httpx logging level
            httpx_logger = logging.getLogger('httpx')
            httpx_logger.setLevel(logging.INFO)
            
            # Clear the thinking indicator and show error
            print("\r" + " " * 25 + "\r", end="", flush=True)
            logger.error(f"Error calling LLM: {str(e)}")
            return f"Error generating response: {str(e)}"
    
    def clear_cache(self):
        """Clear the response cache."""
        if self.verbose:
            logger.info(f"Clearing cache. Had {len(self.cache)} items with {self.cache_hits} hits and {self.cache_misses} misses.")
        self.cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics on the cache usage.
        
        Returns:
            A dictionary with cache statistics
        """
        total_calls = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total_calls if total_calls > 0 else 0
        
        return {
            "cache_size": len(self.cache),
            "max_cache_size": self.max_cache_size,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": hit_rate,
            "cache_enabled": self.use_cache
        }
    
    def test_cache(self, prompt: str, iterations: int = 3) -> Dict[str, Any]:
        """Test the caching functionality by making repeated calls with the same prompt.
        
        Args:
            prompt: The prompt to test with
            iterations: Number of times to call the LLM with the same prompt
            
        Returns:
            A dictionary with test results
        """
        # Make sure caching is enabled for the test
        original_cache_setting = self.use_cache
        self.use_cache = True
        
        # Clear the cache to start fresh
        self.clear_cache()
        
        start_time = time.time()
        results = []
        
        for i in range(iterations):
            iteration_start = time.time()
            response = self._call_llm(prompt)
            iteration_time = time.time() - iteration_start
            
            results.append({
                "iteration": i + 1,
                "time": iteration_time,
                "cache_hit": i > 0,  # First call is always a miss, rest should be hits
                "response_length": len(response)
            })
        
        total_time = time.time() - start_time
        
        # Restore original cache setting
        self.use_cache = original_cache_setting
        
        # Return the results
        return {
            "total_time": total_time,
            "iterations": iterations,
            "avg_time_per_call": total_time / iterations,
            "first_call_time": results[0]["time"],
            "avg_cached_call_time": sum(r["time"] for r in results[1:]) / max(1, len(results) - 1) if len(results) > 1 else 0,
            "cache_stats": self.get_cache_stats(),
            "detailed_results": results
        }
    
    def _create_agent_prompts(self) -> Dict[str, ChatPromptTemplate]:
        """Create prompts for each agent in the swarm.
        
        Returns:
            A dictionary of agent prompts
        """
        prompts = {
            "StrategicAdvisor": ChatPromptTemplate.from_template(STRATEGIC_ADVISOR_PROMPT),
            "BeliefSystemAnalyzer": ChatPromptTemplate.from_template(BELIEF_SYSTEM_ANALYZER_PROMPT),
            "PatternRecognizer": ChatPromptTemplate.from_template(PATTERN_RECOGNIZER_PROMPT),
            "ExecutionEngineer": ChatPromptTemplate.from_template(EXECUTION_ENGINEER_PROMPT),
            "DecisionFramer": ChatPromptTemplate.from_template(DECISION_FRAMER_PROMPT),
            "ChallengeDesigner": ChatPromptTemplate.from_template(CHALLENGE_DESIGNER_PROMPT)
        }
        return prompts
    
    def _agent_handler(self, state: SwarmState, agent_name: str) -> Dict[str, Any]:
        """Handle a specific agent's processing.
        
        Args:
            state: The current state
            agent_name: The name of the agent
            
        Returns:
            Updated state
        """
        # Provide a clean stage header with emoji and agent name
        agent_emojis = {
            "StrategicAdvisor": "🧠",
            "BeliefSystemAnalyzer": "🔍",
            "PatternRecognizer": "🔄",
            "ExecutionEngineer": "⚙️",
            "DecisionFramer": "🛠️",
            "ChallengeDesigner": "🏆"
        }
        emoji = agent_emojis.get(agent_name, "🤖")
        
        print(f"\n{emoji} {agent_name.upper()}")
        
        if self.verbose:
            logger.info(f"Processing with agent: {agent_name}")
        
        # Get the previous analysis if any
        previous_analysis = ""
        if state.get("conversation"):
            previous_messages = []
            for msg in state["conversation"]:
                agent = msg.get("agent", "Unknown")
                content = msg.get("content", "")
                if content:
                    previous_messages.append(f"{agent}: {content}")
            
            if previous_messages:
                previous_analysis = "PREVIOUS ANALYSES:\n" + "\n\n".join(previous_messages)
        
        # Create agent prompt
        prompt_template = self.prompts[agent_name]
        
        # Format the agent descriptions for handoffs
        agent_descriptions = []
        for agent, description in AGENT_SPECS.items():
            if agent != agent_name:  # Don't include the current agent
                agent_descriptions.append(f"- {agent}: {description}")
        
        # Format the prompt
        prompt = prompt_template.format_messages(
            query=state["query"],
            context=f"CONTEXT: {json.dumps(state['context'])}" if state.get("context") else "",
            previous_analysis=previous_analysis,
            agent_descriptions="\n".join(agent_descriptions) if agent_name == "StrategicAdvisor" else ""
        )[0].content
        
        # Display the prompt if verbose output is enabled
        if self.verbose_output:
            print(f"\n📝 PROMPT FOR {agent_name}:")
            print("-" * 40)
            print(prompt)
            print("-" * 40)
        
        # Call the LLM
        response = self._call_llm(prompt)
        
        # Only display the response in verbose mode
        if self.verbose_output:
            print(f"\n📣 RESPONSE FROM {agent_name}:")
            print("-" * 40)
            print(response)
            print("-" * 40)
        
        # Process the response
        if "HANDOFF TO" in response:
            # Extract the target agent and query
            handoff_parts = response.split("HANDOFF TO ", 1)[1]
            target_agent = handoff_parts.split(":", 1)[0].strip()
            handoff_query = handoff_parts.split(":", 1)[1].strip() if ":" in handoff_parts else state["query"]
            
            # Add this message to the conversation
            state["conversation"].append({
                "agent": agent_name,
                "content": response,
                "timestamp": time.time()
            })
            
            # Update the active agent
            state["active_agent"] = target_agent
            
            # Display a simplified handoff message
            next_emoji = agent_emojis.get(target_agent, "🤖")
            print(f"  Consulting with {next_emoji} {target_agent}...")
            
            return {"active_agent": target_agent, "conversation": state["conversation"]}
        
        elif "FINAL ANALYSIS" in response and agent_name == "StrategicAdvisor":
            # This is the final response from the Strategic Advisor
            # Add this message to the conversation
            state["conversation"].append({
                "agent": agent_name,
                "content": response,
                "timestamp": time.time()
            })
            
            # Extract structured components
            final_response = self._extract_final_response(response)
            
            # Update the state with the final response
            state["final_response"] = final_response
            
            # Simple completion message
            print("  Generating final strategic advice...")
            
            return {"conversation": state["conversation"], "final_response": final_response}
        
        else:
            # Regular response, add to conversation
            state["conversation"].append({
                "agent": agent_name,
                "content": response,
                "timestamp": time.time()
            })
            
            # If we're not the strategic advisor, hand back
            if agent_name != "StrategicAdvisor":
                print(f"  Analysis complete, returning to 🧠 Strategic Advisor")
                return {"active_agent": "StrategicAdvisor", "conversation": state["conversation"]}
            
            return {"conversation": state["conversation"]}
    
    def _create_swarm(self):
        """Create the agent swarm using langgraph-swarm.
        
        Returns:
            The configured swarm
        """
        from langgraph.graph import StateGraph, END
        
        # Create a saver for checkpointing
        saver = InMemorySaver()
        
        # Create agents for the swarm
        agents = self._create_agents()
        
        # Define the state schema
        class SwarmState(TypedDict):
            messages: List[Dict[str, str]]
            active_agent: str
        
        # Create the state graph
        graph = StateGraph(SwarmState)
        
        # Add nodes for each agent
        for agent in agents:
            graph.add_node(agent["name"], agent["function"])
        
        # Define the router
        def router(state: SwarmState):
            # Get the active agent
            active_agent = state.get("active_agent", "StrategicAdvisor")
            
            # Check if the active agent exists in our agents
            agent_names = [a["name"] for a in agents]
            if active_agent not in agent_names:
                # Default to StrategicAdvisor if the active agent is not found
                return "StrategicAdvisor"
                
            return active_agent
        
        # Add conditional edges
        for agent in agents:
            # Each agent can transition to any other agent
            destinations = [a["name"] for a in agents if a["name"] != agent["name"]]
            graph.add_conditional_edges(
                agent["name"],
                router,
                {name: name for name in destinations}
            )
        
        # Set the entry point
        graph.set_entry_point("StrategicAdvisor")
        
        # Compile the graph
        return graph.compile(checkpointer=saver)
    
    def _create_agents(self):
        """Create the agents for the swarm.
        
        Returns:
            A list of agents
        """
        from langchain.agents import AgentExecutor, create_openai_tools_agent
        from langchain_core.messages import AIMessage, HumanMessage
        
        agents = []
        
        # Create a handoff tool for each agent
        handoff_tools = {}
        for agent_name in self.prompts.keys():
            handoff_tools[agent_name] = self._create_handoff_tool(agent_name)
        
        # Create an agent for each prompt
        for agent_name, prompt in self.prompts.items():
            # Get the tools for this agent (all handoff tools except its own)
            tools = [tool for name, tool in handoff_tools.items() if name != agent_name]
            
            # Create a simple agent function
            def create_agent_fn(agent_name, prompt_template):
                def agent_fn(state):
                    # Extract messages from state
                    messages = state.get("messages", [])
                    
                    # Format the prompt with the messages
                    if messages:
                        last_message = messages[-1]["content"]
                        
                        # Format the agent descriptions for handoffs
                        agent_descriptions = []
                        for agent, description in AGENT_SPECS.items():
                            if agent != agent_name:  # Don't include the current agent
                                agent_descriptions.append(f"- {agent}: {description}")
                        
                        # Format the prompt
                        formatted_prompt = prompt_template.format_messages(
                            query=last_message,
                            context="",
                            previous_analysis="",
                            agent_descriptions="\n".join(agent_descriptions) if agent_name == "StrategicAdvisor" else ""
                        )[0].content
                    else:
                        # Format the prompt with a default message
                        formatted_prompt = prompt_template.format_messages(
                            query="No query provided",
                            context="",
                            previous_analysis="",
                            agent_descriptions=""
                        )[0].content
                    
                    # Call the LLM
                    response = self._call_llm(formatted_prompt)
                    
                    # Update the messages
                    new_messages = messages + [{"role": "assistant", "content": response}]
                    
                    # Return the updated state
                    return {"messages": new_messages, "active_agent": agent_name}
                
                return agent_fn
            
            # Add the agent to the list
            agents.append({
                "name": agent_name,
                "function": create_agent_fn(agent_name, prompt)
            })
        
        return agents
    
    def _create_handoff_tool(self, agent_name):
        """Create a handoff tool for an agent.
        
        Args:
            agent_name: The name of the agent to hand off to
            
        Returns:
            A handoff tool
        """
        from langgraph_swarm import create_handoff_tool
        
        # Create a description for the handoff tool
        descriptions = {
            "StrategicAdvisor": "Transfer to the Strategic Advisor for high-level guidance and coordination",
            "BeliefSystemAnalyzer": "Transfer to the Belief System Analyzer to examine underlying beliefs and assumptions",
            "PatternRecognizer": "Transfer to the Pattern Recognizer to identify recurring patterns and behaviors",
            "ExecutionEngineer": "Transfer to the Execution Engineer to develop practical implementation steps",
            "DecisionFramer": "Transfer to the Decision Framer to structure decision-making processes",
            "ChallengeDesigner": "Transfer to the Challenge Designer to create growth-oriented challenges"
        }
        
        description = descriptions.get(agent_name, f"Transfer to {agent_name}")
        
        # Create the handoff tool
        return create_handoff_tool(agent_name=agent_name, description=description)
    
    def _extract_final_response(self, response: str) -> Dict[str, Any]:
        """Extract structured components from the final response.
        
        Args:
            response: The raw final response
            
        Returns:
            A structured response dictionary
        """
        # Initialize response components
        hard_truth = ""
        actions = []
        challenge = ""
        final_analysis = ""
        original_agent_insights = ""
        
        # Split into sections
        sections = response.split("\n\n")
        current_section = None
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
            
            if "FINAL ANALYSIS:" in section:
                current_section = "final_analysis"
                final_analysis = section.replace("FINAL ANALYSIS:", "").strip()
            elif "HARD TRUTH:" in section:
                current_section = "hard_truth"
                hard_truth = section.replace("HARD TRUTH:", "").strip()
            elif "ACTIONS:" in section:
                current_section = "actions"
                action_lines = [line.strip() for line in section.split("\n")[1:] if line.strip()]
                actions = []
                for line in action_lines:
                    # Remove any leading numbers or bullet points
                    if line[0].isdigit() and ". " in line:
                        actions.append(line.split(". ", 1)[1])
                    elif line.startswith("- "):
                        actions.append(line[2:])
                    else:
                        actions.append(line)
            elif "CHALLENGE:" in section:
                current_section = "challenge"
                challenge = section.replace("CHALLENGE:", "").strip()
            elif "ORIGINAL AGENT INSIGHTS:" in section:
                current_section = "original_agent_insights"
                # Store the whole insights section as a string
                original_agent_insights = section.replace("ORIGINAL AGENT INSIGHTS:", "").strip()
            elif current_section == "final_analysis":
                final_analysis += "\n\n" + section
            elif current_section == "hard_truth":
                hard_truth += "\n\n" + section
            elif current_section == "actions":
                action_lines = [line.strip() for line in section.split("\n") if line.strip()]
                for line in action_lines:
                    # Remove any leading numbers or bullet points
                    if line[0].isdigit() and ". " in line:
                        actions.append(line.split(". ", 1)[1])
                    elif line.startswith("- "):
                        actions.append(line[2:])
                    else:
                        actions.append(line)
            elif current_section == "challenge":
                challenge += "\n\n" + section
            elif current_section == "original_agent_insights":
                # Append to the original agent insights
                original_agent_insights += "\n\n" + section
        
        # If we couldn't extract a hard truth, use the first section as a fallback
        if not hard_truth and sections:
            hard_truth = sections[0]
        
        # Create the final response
        final_response = {
            "hard_truth": hard_truth,
            "actions": actions,
            "challenge": challenge,
            "final_analysis": final_analysis,
            "original_agent_insights": original_agent_insights
        }
        
        return final_response
    
    def generate_advice(self, query: str, context: Optional[Dict[str, Any]] = None, max_iterations: int = 6) -> Dict[str, Any]:
        """
        Generate strategic advice based on the user query.

        Args:
            query: The user's query
            context: Optional context dictionary
            max_iterations: Maximum number of swarm iterations

        Returns:
            Dictionary containing the strategic advice
        """
        # Initialize
        session_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Announce the start
        print(f"\n📋 STARTING STRATEGIC ADVISOR (SWARM ARCHITECTURE)")
        print(f"Query: {query}")
        
        # Only print the query (not the debug info)
        # print("\n🚀 STARTING STRATEGIC ANALYSIS")
        
        # Create the initial state
        state = {
            "query": query,
            "context": {},
            "active_agent": "StrategicAdvisor",
            "conversation": []
        }
        
        if context:
            state["context"] = {"provided_context": context}
        
        try:
            # Start with the strategic advisor
            result = self._agent_handler(state, "StrategicAdvisor")
            state.update(result)
            
            # Continue processing as long as there's no final response
            while "final_response" not in state:
                # Check which agent is active
                active_agent = state.get("active_agent", "StrategicAdvisor")
                
                # Call the active agent
                result = self._agent_handler(state, active_agent)
                state.update(result)
                
                # If we've been through too many iterations, stop
                if len(state.get("conversation", [])) > 10:
                    print("\n⚠️ Analysis completed with maximum iterations")
                    break
            
            # Extract the final response
            if "final_response" in state:
                response = state["final_response"]
            else:
                # Fallback: try to extract a response from the conversation
                last_message = state.get("conversation", [])[-1] if state.get("conversation") else None
                if last_message and "content" in last_message:
                    response = self._extract_final_response(last_message["content"])
                else:
                    # If all else fails, return a simple response
                    response = {
                        "hard_truth": "No structured response could be generated.",
                        "actions": ["Review the conversation history for insights."],
                        "challenge": "Try reformulating your query to be more specific."
                    }
            
            # Add metadata
            response["session_id"] = session_id
            response["execution_time"] = time.time() - start_time
            
            # Save the response
            self._save_response(response)
            
            # Print completion message with timing
            print(f"\n✅ ANALYSIS COMPLETE ({response['execution_time']:.1f}s)")
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error generating advice: {e}")
            print(f"\n❌ ERROR: {str(e)}")
            raise
    
    def _save_response(self, response: Dict[str, Any]) -> None:
        """Save the response to a file.
        
        Args:
            response: The response to save
        """
        # Create the output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Generate a filename
        session_id = response.get("session_id", str(uuid.uuid4()))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"strategic_advice_{timestamp}_{session_id[:8]}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        # Save the response
        with open(filepath, "w") as f:
            json.dump(response, f, indent=2)
        
        self.logger.info(f"Response saved to {filepath}") 