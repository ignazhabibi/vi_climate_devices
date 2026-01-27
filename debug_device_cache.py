from vi_api_client.mock_client import MockViClient
import asyncio
import dataclasses


async def main():
    client = MockViClient(device_name="Vitocal250A")
    installations = await client.get_full_installation_status(None)
    # Corrected: List contains Devices directly
    device = installations[0]

    target = "heating.dhw.pumps.circulation.status"

    # 1. Check initial state
    feat = device.get_feature(target)
    print(f"Initial: {feat.value}")

    # 2. Modify features LIST
    found_idx = -1
    for i, f in enumerate(device.features):
        if f.name == target:
            found_idx = i
            break

    if found_idx != -1:
        print("Modifying list at index", found_idx)
        new_feat = dataclasses.replace(device.features[found_idx], value="standby")
        device.features[found_idx] = new_feat

    # 3. Check get_feature again
    feat_after = device.get_feature(target)
    print(f"After List Update: {feat_after.value}")

    if feat_after.value == "standby":
        print("SUCCESS: List update propagated")
    else:
        print("FAILURE: get_feature returned old value!")
        # Hint: check _features_by_name if it exists
        if hasattr(device, "_features_by_name"):
            cached = device._features_by_name.get(target)
            print(f"Internal Cache Value: {cached.value}")


if __name__ == "__main__":
    asyncio.run(main())
