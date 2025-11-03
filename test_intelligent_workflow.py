#!/usr/bin/env python3
"""
Test script for the new Intelligent Workflow Selection
Tests different prompts and shows which models/styles are selected
Claude - November 3, 2025
"""

import sys
sys.path.append('/home/tkash/wsl_dev/open-chat/backend')

from services.workflow_intelligence import WorkflowIntelligence, ModelSelector

def test_intelligent_selection():
    """Test the intelligent model and style selection"""
    
    test_cases = [
        # Realistic requests
        ("show me a photorealistic portrait of a person", None),
        ("create a hyperrealistic city street", None),
        ("draw a realistic landscape photo", None),
        
        # Semi-realistic/cartoon
        ("show me a cartoon character design", None),
        ("create a stylized illustration of a hero", None),
        ("draw a semi-realistic animal", None),
        
        # Artistic requests
        ("paint a beautiful sunset", None),
        ("create an artistic interpretation of music", None),
        ("show me a beautiful garden painting", None),
        
        # Concept art
        ("visualize a futuristic sci-fi cityscape", None),
        ("create concept art for a fantasy world", None),
        ("show me a cinematic space battle", None),
        
        # Test with explicit style
        ("draw a mountain", "very_realistic"),
        ("show me a sunset", "semi_realistic"),
    ]
    
    print("🧠 INTELLIGENT WORKFLOW SELECTION TEST")
    print("=" * 60)
    
    for prompt, explicit_style in test_cases:
        print(f"\n📝 Prompt: {prompt}")
        if explicit_style:
            print(f"👤 User Style: {explicit_style}")
        
        # Test the workflow creation
        config = WorkflowIntelligence.create_intelligent_workflow(prompt, explicit_style)
        
        print(f"🎨 Selected Style: {config['style']}")
        print(f"🤖 Model: {config['model']}")
        print(f"⚙️  Parameters: {config['parameters']['steps']} steps, CFG {config['parameters']['cfg']}")
        print(f"📐 Dimensions: {config['parameters']['width']}x{config['parameters']['height']}")
        print(f"✨ Enhanced Prompt: {config['prompt'][:80]}...")
        print(f"🚫 Negative: {config['negative_prompt'][:50]}...")

if __name__ == "__main__":
    test_intelligent_selection()