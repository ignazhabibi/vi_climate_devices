from vi_api_client.mock_client import MockViClient
import asyncio


async def main():
    try:
        client = MockViClient(device_name="Vitocal250A")
        print("Loading...")
        resp = await client.get_full_installation_status(installation_id=None)
        print(f"Response Type: {type(resp)}")

        if isinstance(resp, list):
            print(f"List length: {len(resp)}")
            if len(resp) > 0:
                print(f"Item 0 Type: {type(resp[0])}")
                try:
                    print(f"Item 0 vars: {vars(resp[0]).keys()}")
                except:
                    print(f"Item 0 dir: {dir(resp[0])}")
        else:
            print(f"Vars: {vars(resp).keys()}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
