from vi_api_client.mock_client import MockViClient
import asyncio
import sys


async def main():
    try:
        client = MockViClient(device_name="Vitocal250A")

        # Force load
        print("Loading data...")
        installations = await client.get_full_installation_status(installation_id=None)

        # Access device
        device = installations[0].gateways[0].devices[0]
        print(f"Device: {device.model_id}")

        # Find feature
        feat_name = "heating.dhw.pumps.circulation.status"
        feature = device.get_feature(feat_name)
        print(f"Original Value: {feature.value}")

        # Modify
        feature.value = "standby"
        print("Modified value to standby")

        # Simulate Integration doing update
        # Integration calls get_full_installation_status or update_device
        # Let's call get_full_installation_status again to see if it returns cached/modified object
        print("Fetching again...")
        installations2 = await client.get_full_installation_status(installation_id=None)
        device2 = installations2[0].gateways[0].devices[0]
        feature2 = device2.get_feature(feat_name)

        print(f"Value after fetch: {feature2.value}")

        if feature2.value == "standby":
            print("SUCCESS: Modification persisted")
        else:
            print("FAILURE: Modification lost")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
