from .simulator import simulate_network

def apply_network_config(config: dict):
    print(f"📶 Applying Network Config: {config}")

    result = simulate_network(config)

    return result
