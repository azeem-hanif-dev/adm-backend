# ai_agents.py
import os
import textwrap
import logging
from datetime import datetime
from dotenv import load_dotenv
from openai import AsyncOpenAI
import re
from typing import Dict, Any, Optional, List


load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class CampaignAI:
    """
    Unified AI agent class for Megan, Anna, and Ashley.
    Each agent handles different company types with specialized personas.
    """

    def __init__(self):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("Missing DEEPSEEK_API_KEY")

        # Initialize DeepSeek client (shared by all agents)
        self.client = AsyncOpenAI(  # <-- AsyncOpenAI
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )

        # ============================================
        # AGENT CONFIGURATIONS
        # ============================================

        # Cappah International Company Profile (for Megan and Ashley)
        self.cappah_profile = textwrap.dedent(
            """
            Cappah International is a global manufacturer and supplier of professional
            cleaning and facility-maintenance products, serving customers across Europe
            and the GCC.

            We work closely with distributors, wholesalers, and large end-users,
            offering consistent quality, reliable supply, and long-term commercial
            partnerships. Our focus is on practical, durable solutions supported by
            responsive service and efficient logistics.
            """
        ).strip()

        # DCS Products Company Profile (for Anna)
        self.dcs_profile = textwrap.dedent(
            """
            DCS Products is a specialized division focused on commercial cleaning
            equipment and supplies. We serve professional cleaning companies and
            large facilities with top-tier products and dedicated technical support.

            Our product range includes advanced cleaning machines, specialized
            chemicals, and facility maintenance solutions designed for commercial
            and industrial applications.
            """
        ).strip()

        # Agent configurations
        self.agent_configs = {
            "megan": {
                "persona": "Megan Henderson — Customer Relations & Account Development",
                "company_types": ["customers"],
                "company_profile": self.cappah_profile,
                "system_prompt": self._get_megan_system_prompt(),
                "requires_greeting": True,
                "supports_dutch": True,
                "default_temperature": 1.3,
                "role": "customer_relations",
                "target_audience": "existing customers"
            },
            "anna": {
                "persona": "Anna — DCS Products Specialist",
                "company_types": ["dcs_customers"],
                "company_profile": self.dcs_profile,
                "system_prompt": self._get_anna_system_prompt(),
                "requires_greeting": True,
                "supports_dutch": False,
                "default_temperature": 1.2,
                "role": "product_specialist",
                "target_audience": "DCS customers and leads"
            },
            "ashley": {
                "persona": "Ashley Parker — Lead Manager, GCC Region",
                "company_types": ["gcc_leads"],
                "company_profile": self.cappah_profile,
                "system_prompt": self._get_ashley_system_prompt(),
                "requires_greeting": True,
                "supports_dutch": False,
                "default_temperature": 1.3,
                "role": "lead_manager",
                "target_audience": "GCC region leads"
            }
        }

    # ============================================
    # AGENT-SPECIFIC SYSTEM PROMPTS
    # ============================================

    def _get_megan_system_prompt(self) -> str:
        """Megan's system prompt for existing customers."""
        return textwrap.dedent(
            """
            You are Megan Henderson from Cappah International.
            You manage ongoing customer relationships and existing accounts.

            These emails are sent ONLY to existing customers.
            A commercial relationship already exists.
            You must make sure to write how we care about the customers and are introducing our new line exclusively to them.    

            Your tone is:
            - Professional
            - Confident
            - Warm
            - Familiar (but never casual)
            - Human and thoughtful (never salesy or robotic)

            Core behavior rules:
            - Introduce yourself as the new Marketing Manager from Cappah International unless if there is conversation history. If there has been an email sent by you beforehand do not re-introduce yourself.  
            - NEVER explain who Cappah International is from scratch
            - Write as someone the customer already knows
            - Make sure the product being mentioned is in bold and has the first letter as capital.
            - Assume prior purchases or discussions, without inventing details
            - Acknowledge continuity subtly but also if there is history just start with something like we have news about a new product or something better for a campaign.  
            - Do not ask for 1 word replies for more information make sure to try and schedule calls or to send a catalog or send more information 
            - Do not create any information that you do not have or is from the database.
            - Do not create any products we do not have.
            - Do not mention Ltd/B.V or any other addition in company name that is just an addition like pvt ltd. Mention the Company's actual name so it seems more personal.

            Writing rules:
            - Write short B2B customer emails (around 100 words)
            - Output valid HTML only (<p>, <strong>, <ul>, <li>, <br>)
            - Do NOT include a signature
            - One natural call-to-action per email
            - Do NOT invent product names, SKUs, certifications, or specs
            - Only reference products explicitly provided in context
            - Do NOT overuse product lists — keep it conversational
            - The email should feel like it was written manually by a real account manager
            - Make sure each email is catered to the customer specifically not just recycled mails to multiple customers

            GREETING RULE (MANDATORY):
            - The email MUST start with a greeting.
            - If customer person_name is present:
            - Start with: Hi person_name,
            - If customer person_name is NOT present:
            - Start EXACTLY with: Hi company_name Team,
            - NEVER use:
            - "Dear Customer"
            - "Dear Valued Customer"
            - "Dear Sir/Madam"
            - "Hi Customer"
            - Any generic greeting
            - This rule overrides all stylistic preferences.
            - Make sure that when writing in another language you do not repeat the greeting twice.
            - Start the email immediately. No meta-talk.

            STRICT OUTPUT RULES:
            1. Output ONLY valid HTML (tags: <p>, <strong>, <ul>, <li>, <br>).
            2. NEVER include introductory text like "Here is the email" or "I have written this for you."
            3. START directly with the greeting and END with the final sentence. 
            4. Tone: Professional, Warm, Familiar but not casual.
            5. Content: Focus EXCLUSIVELY on the products provided. Do not mention any other cleaning supplies.
            6. Bold the **Product Name** and capitalize its first letter.
            """
        ).strip()

    def _get_anna_system_prompt(self) -> str:
        """Anna's system prompt for DCS customers."""
        return textwrap.dedent(
            """
            You are Anna from DCS Products.
            You are a specialist for DCS cleaning equipment and supplies.

            Your tone is:
            - Professional
            - Technical but clear
            - Solution-focused
            - Knowledgeable
            - Direct and efficient

            Core behavior rules:
            - Focus on DCS products and their technical advantages
            - Emphasize durability, efficiency, and commercial benefits
            - Provide clear specifications when available
            - Make sure the product being mentioned is in bold and has the first letter as capital.
            - Do not create any information that you do not have or is from the database.
            - Do not create any products we do not have.
            - Position DCS as the premium choice for commercial cleaning

            Writing rules:
            - Write technical B2B emails (around 100-120 words)
            - Output valid HTML only (<p>, <strong>, <ul>, <li>, <br>)
            - Do NOT include a signature
            - One clear technical or commercial call-to-action
            - Do NOT invent product names, SKUs, certifications, or specs
            - Only reference products explicitly provided in context
            - Include relevant technical details when appropriate

            GREETING RULE (MANDATORY):
            - The email MUST start with a greeting.
            - If customer person_name is present:
            - Start with: Hi person_name,
            - If customer person_name is NOT present:
            - Start EXACTLY with: Hi company_name Team,
            - NEVER use generic greetings

            STRICT OUTPUT RULES:
            1. Output ONLY valid HTML (tags: <p>, <strong>, <ul>, <li>, <br>).
            2. NEVER include introductory text like "Here is the email" or "I have written this for you."
            3. START directly with the greeting and END with the final sentence. 
            4. Tone: Professional, Technical, Solution-focused.
            5. Bold the **Product Name** and capitalize its first letter.
            6. Write ONLY in English.
            """
        ).strip()

    def _get_ashley_system_prompt(self) -> str:
        """Ashley's system prompt for GCC leads."""
        return textwrap.dedent(
            """
            You are Ashley Parker from Cappah International.
            You manage all leads for Cappah International in the GCC region.
            These emails are sent to potential leads who are not yet customers.
            
            IMPORTANT: All emails must be written in English only.

            Your tone is:
            - Professional
            - Confident
            - Warm and engaging
            - Approachable but business-focused
            - Clear and direct

            Core behavior rules:
            - ALWAYS introduce yourself and Cappah International (since these are leads)
            - Position Cappah as a professional cleaning solutions provider
            - Focus on building new relationships in the GCC region
            - Make sure the product being mentioned is in bold and has the first letter as capital.
            - Do not assume any prior relationship or knowledge of our company
            - Always mention the campaign/offer as the main reason for reaching out
            - Aim to schedule calls or meetings to discuss further
            - Do not create any information that you do not have or is from the database.
            - Do not create any products we do not have.
            - Mention the company as "Cappah International" (not Ltd/B.V or other legal suffixes)

            Writing rules:
            - Write clear B2B lead emails (around 100-120 words)
            - Output valid HTML only (<p>, <strong>, <ul>, <li>, <br>)
            - Do NOT include a signature
            - One clear call-to-action per email (schedule call, send info, etc.)
            - Do NOT invent product names, SKUs, certifications, or specs
            - Only reference products explicitly provided in context
            - The email should feel like it was written by a professional lead manager
            - Always include an introduction of yourself and the company
            
            GREETING RULE (MANDATORY):
            - The email MUST start with a greeting.
            - If lead person_name is present:
            - Start with: Hi person_name,
            - If lead person_name is NOT present:
            - Start EXACTLY with: Hi company_name Team,
            - NEVER use:
            - "Dear Customer"
            - "Dear Valued Customer"
            - "Dear Sir/Madam"
            - "Hi Customer"
            - Any generic greeting
            - This rule overrides all stylistic preferences.
            - Start the email immediately. No meta-talk.
            
            STRUCTURE RULE (MANDATORY):
            1. Introduction of yourself and Cappah International
            2. Brief mention of your role in GCC region
            3. Introduction of the campaign/offer
            4. Value proposition
            5. Clear call-to-action
            
            STRICT OUTPUT RULES:
            1. Output ONLY valid HTML (tags: <p>, <strong>, <ul>, <li>, <br>).
            2. NEVER include introductory text like "Here is the email" or "I have written this for you."
            3. START directly with the greeting and END with the final sentence. 
            4. Tone: Professional, Warm, Engaging, Business-focused.
            5. Content: Focus on introducing the company and the campaign.
            6. Bold the **Product Name** and capitalize its first letter.
            7. Write ONLY in English.
            """
        ).strip()

    # ============================================
    # AGENT SELECTION HELPERS
    # ============================================

    def get_agent_by_company_type(self, company_type: str) -> str:
        """Map company_type to appropriate agent."""
        mapping = {
            "customers": "megan",
            "dcs_customers": "anna",
            "gcc_leads": "ashley"
        }
        agent = mapping.get(company_type)
        if not agent:
            raise ValueError(f"Unknown company_type: {company_type}. Must be: customers, dcs_customers, or gcc_leads")
        return agent

    def get_agent_info(self, agent_name: str) -> Dict[str, Any]:
        """Get configuration info for a specific agent."""
        if agent_name in self.agent_configs:
            return self.agent_configs[agent_name]
        raise ValueError(f"Unknown agent: {agent_name}. Must be: megan, anna, or ashley")

    # ============================================
    # COMMON UTILITY METHODS
    # ============================================

    def enforce_greeting(self, html: str, customer_info: dict, agent_name: str) -> str:
        """Apply greeting rule based on agent requirements."""
        config = self.agent_configs.get(agent_name, {})
        if not config.get("requires_greeting", True):
            return html

        person = customer_info.get("person_name")
        company = customer_info.get("company_name")
        
        greeting = f"<p>Hi {person},</p>" if person else f"<p>Hi {company} Team,</p>"
        
        # Clean up any AI-generated greeting or markdown code blocks
        html = re.sub(r"```html|```", "", html)
        html = re.sub(r"^\s*<p>\s*(hi|dear|hello)[^<]*?</p>", "", html, flags=re.IGNORECASE | re.MULTILINE)
        
        return greeting + html.strip()

    def _append_language_instruction(self, prompt: str, customer_info: dict, agent_name: str) -> str:
        """Add language instruction for Dutch customers (Megan only)."""
        config = self.agent_configs.get(agent_name, {})
        if not config.get("supports_dutch", False):
            return prompt
        
        country_value = customer_info.get("country", "")
        if country_value is None:
            country = ""
        else:
            country = str(country_value).strip().lower()
        
        if country in ["netherlands", "nl", "nederland"]:
            prompt += "\n\nIMPORTANT: Write this email in Dutch, keeping the same professional, warm, and personal style."
        return prompt

    async def _call_deepseek(self, messages: list, temperature: float = 1.3):
        """Make DeepSeek API call with reasoning enabled."""
        return await self.client.chat.completions.create(
             model="deepseek-reasoner",
            messages=messages,
            #temperature=temperature,
            max_tokens=4000,
            stream=False,
        )

    def _extract_html(self, response) -> str:
        """Extract HTML content from DeepSeek response."""
        try:
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error extracting HTML from response: {e}")
            return ""

    def _build_conversation_record(
        self,
        customer_id: str,
        html: str,
        agent_name: str,
        message_type: str = "campaign",
        campaign_name: Optional[str] = None,
    ) -> dict:
        """Build conversation record for database."""
        return {
            "customer_id": customer_id,
            "role": agent_name,
            "type": message_type,
            "campaign_name": campaign_name,
            "content": html,
            "created_at": datetime.utcnow(),
        }

    # ============================================
    # MAIN CAMPAIGN GENERATION METHOD
    # ============================================

    async def generate_campaign_message(
        self,
        customer_id: str,
        customer_info: Dict[str, Any],
        campaign_name: str,
        campaign_prompt: str,
        agent_name: Optional[str] = None,
        company_type: Optional[str] = None,
        recent_messages: Optional[List[dict]] = None,
        campaign_history: Optional[List[dict]] = None,
        featured_products: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        """
        Generate campaign email message using specified agent.
        
        Args:
            customer_id: Customer identifier (email)
            customer_info: Dictionary with person_name, company_name, email, country
            campaign_name: Name of the campaign
            campaign_prompt: Detailed campaign instructions
            agent_name: Explicit agent name (megan, anna, ashley)
            company_type: Company type (customers, dcs_customers, gcc_leads)
            recent_messages: Recent conversation history
            campaign_history: Previous campaign emails
            featured_products: Products to feature in the campaign
            
        Returns:
            Dict with 'html' and 'conversation_record'
        """
        # Determine which agent to use
        if agent_name:
            agent = agent_name.lower()
            if agent not in self.agent_configs:
                raise ValueError(f"Unknown agent: {agent}. Must be one of: {list(self.agent_configs.keys())}")
        elif company_type:
            agent = self.get_agent_by_company_type(company_type)
        else:
            # Default to Megan for backward compatibility
            agent = "megan"
            logger.warning("No agent_name or company_type specified, defaulting to 'megan'")

        # Get agent configuration
        config = self.agent_configs[agent]
        recent_messages = recent_messages or []
        campaign_history = campaign_history or []
        featured_products = featured_products or []

        # Build messages list
        messages = [
            {"role": "system", "content": config["system_prompt"]},
            {"role": "system", "content": f"Company Profile:\n{config['company_profile']}"},
            {"role": "system", "content": f"Campaign: {campaign_name}"},
            {"role": "system", "content": f"Campaign Brief:\n{campaign_prompt}"},
            {
                "role": "system",
                "content": (
                    f"Customer Information:\n"
                    f"- Name: {customer_info.get('person_name', 'Customer')}\n"
                    f"- Company: {customer_info.get('company_name', '')}\n"
                    f"- Email: {customer_info.get('email', '')}\n"
                    f"- Country: {customer_info.get('country', '')}"
                ),
            },
        ]

        # Add conversation history if available
        if recent_messages:
            convo = "Recent conversation:\n"
            for m in recent_messages:
                role = agent.capitalize() if m.get("role") == agent else "Customer"
                convo += f"{role}: {m.get('content', '')}\n"
            messages.append({"role": "system", "content": convo})

        # Add campaign history if available
        if campaign_history:
            history = "Previous campaigns:\n"
            for c in campaign_history[-3:]:
                history += f"- {c.get('campaign_name', 'Unknown')}\n"
            messages.append({"role": "system", "content": history})

        # Add featured products if available
        if featured_products:
            prod = "\n".join(
                f"{p.get('name', 'Product')} — {p.get('description', '')[:120]}"
                for p in featured_products[:4]
            )
            messages.append({"role": "system", "content": f"Campaign products:\n{prod}"})

        # Build user prompt based on agent
        user_prompt = self._build_agent_specific_prompt(agent, customer_info, campaign_name)
        
        # Add language instruction for Megan if needed
        user_prompt = self._append_language_instruction(user_prompt, customer_info, agent)
        
        messages.append({"role": "user", "content": user_prompt})

        # Call DeepSeek API
        try:
            response = await self._call_deepseek(messages, temperature=config["default_temperature"])
            html = self._extract_html(response)
            
            if not html:
                html = self._get_fallback_html(agent, customer_info)
            
            # Apply greeting rule
            html = self.enforce_greeting(html, customer_info, agent)
            
        except Exception as e:
            logger.error(f"Error generating campaign message with agent {agent}: {e}")
            html = self._get_fallback_html(agent, customer_info)

        return {
            "html": html,
            "conversation_record": self._build_conversation_record(
                customer_id=customer_id,
                html=html,
                agent_name=agent,
                message_type="campaign",
                campaign_name=campaign_name,
            ),
        }

    def _build_agent_specific_prompt(self, agent_name: str, customer_info: dict, campaign_name: str) -> str:
        """Build agent-specific user prompt."""
        person_name = customer_info.get('person_name', 'Customer')
        company_name = customer_info.get('company_name', '')
        
        if agent_name == "megan":
            return (
                f"Write a polished HTML email for trusted customer {person_name} from {company_name}. "
                "Do NOT invent any product names or SKUs. Only reference products in `featured_products` list. "
                "Do not include any placeholder for images; we will insert images programmatically. "
                "Make it warm, professional, concise, and slightly personalized. "
                "Introduce the Campaign as the latest new thing not like a follow up. "
                f"Address {person_name} and refer to their company {company_name}."
            )
        elif agent_name == "anna":
            return (
                f"Write a technical HTML email for {person_name} from {company_name}. "
                "Focus on DCS products and their commercial benefits. "
                "Do NOT invent any product names or SKUs. Only reference products in `featured_products` list. "
                "Do not include any placeholder for images; we will insert images programmatically. "
                "Make it professional, knowledgeable, and solution-oriented. "
                f"Address {person_name} and refer to their company {company_name} as a potential partner for DCS products."
            )
        elif agent_name == "ashley":
            return (
                f"Write a professional HTML email for lead {person_name} from {company_name} in the GCC region. "
                "Start by introducing yourself as Ashley Parker from Cappah International. "
                "Briefly explain what Cappah International does. "
                "Then introduce the campaign as an opportunity for their business. "
                "Do NOT invent any product names or SKUs. Only reference products in `featured_products` list. "
                "Do not include any placeholder for images; we will insert images programmatically. "
                "Make it professional, engaging, and focused on building a new relationship. "
                f"Address {person_name} and refer to their company {company_name} as a potential partner in the GCC region."
            )
        else:
            return "Write a professional HTML email for this campaign."

    def _get_fallback_html(self, agent_name: str, customer_info: dict) -> str:
        """Get fallback HTML if generation fails."""
        person_name = customer_info.get('person_name', 'Customer')
        
        if agent_name == "megan":
            return f"""<p>Hi {person_name},</p>
<p>I wanted to share a quick update about our latest campaign.</p>
<p>If you'd like more details, I'd be happy to provide them.</p>"""
        
        elif agent_name == "anna":
            return f"""<p>Hi {person_name},</p>
<p>I'm Anna from DCS Products.</p>
<p>I'm reaching out to introduce our latest campaign and explore how our solutions could benefit your operations.</p>
<p>Would you be open to a brief discussion about your needs?</p>"""
        
        elif agent_name == "ashley":
            return f"""<p>Hi {person_name},</p>
<p>My name is Ashley Parker, and I'm the Lead Manager for Cappah International in the GCC region.</p>
<p>Cappah International specializes in professional cleaning and facility-maintenance solutions.</p>
<p>I'm writing to introduce our latest campaign which I believe could add value to your operations.</p>
<p>Would you be available for a brief introductory call next week to explore potential synergies?</p>"""
        
        else:
            return f"<p>Hi {person_name},</p><p>I'm writing to introduce our latest campaign.</p>"

    # ============================================
    # CONVENIENCE METHODS FOR SPECIFIC AGENTS
    # ============================================

    def generate_as_megan(self, *args, **kwargs):
        """Explicitly use Megan agent."""
        return self.generate_campaign_message(*args, **kwargs, agent_name="megan")

    def generate_as_anna(self, *args, **kwargs):
        """Explicitly use Anna agent."""
        return self.generate_campaign_message(*args, **kwargs, agent_name="anna")

    def generate_as_ashley(self, *args, **kwargs):
        """Explicitly use Ashley agent."""
        return self.generate_campaign_message(*args, **kwargs, agent_name="ashley")

    # ============================================
    # DIRECT MESSAGE METHODS (for non-campaign emails)
    # ============================================

    def generate_message(
        self,
        customer_id: str,
        customer_info: Dict[str, Any],
        agent_name: Optional[str] = None,
        company_type: Optional[str] = None,
        recent_messages: Optional[List[dict]] = None,
        product_summaries: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a direct (non-campaign) message.
        """
        # Determine which agent to use
        if agent_name:
            agent = agent_name.lower()
            if agent not in self.agent_configs:
                raise ValueError(f"Unknown agent: {agent}")
        elif company_type:
            agent = self.get_agent_by_company_type(company_type)
        else:
            agent = "megan"

        # Similar logic to generate_campaign_message but for direct messages
        # This would be a simplified version without campaign-specific context
        # Implementation would follow similar pattern as above
        
        # For now, return a simple implementation
        config = self.agent_configs[agent]
        html = f"<p>Direct message from {config['persona']}</p>"
        
        return {
            "html": html,
            "conversation_record": self._build_conversation_record(
                customer_id=customer_id,
                html=html,
                agent_name=agent,
                message_type="direct",
            ),
        }