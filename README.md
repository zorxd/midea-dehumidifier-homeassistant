# Midea Dehumidifier (Cloud) for Home Assistant

A HACS custom integration that reads and controls a Midea dehumidifier through the Midea cloud, the same way the Midea app does. Use it when Home Assistant can't reach the dehumidifier on your local network, for example because they are in different buildings. If they are on the same network, a local integration such as [Midea AC LAN](https://github.com/wuwentao/midea_ac_lan) is faster and doesn't depend on Midea's servers.

Tested with a Midea Cube 50-pint dehumidifier and the MSmartHome cloud (the Midea Smart Home app).

## Features

- Humidifier entity: on/off, target humidity (35–85 % in 5 % steps, like the Midea app) and mode (Set, Continuous, Smart, and Dry clothes on models that have it)
- Fan speed select: low, medium, high
- Sensors: humidity, temperature, water level (on models that report it), error code
- Binary sensors: tank full, filter needs cleaning (on models that report it), error, defrosting (disabled by default)

Setting a target humidity switches the dehumidifier to Set mode, since the other modes ignore it.

## Installation

1. In HACS, add this repository as a custom repository of type **Integration**.
2. Download **Midea Dehumidifier (Cloud)**.
3. Restart Home Assistant.
4. Go to **Settings -> Devices & services -> Add integration** and search for **Midea Dehumidifier (Cloud)**.
5. Enter the e-mail and password of your Midea account and choose the app it belongs to. Accounts from the Midea Smart Home app are **MSmartHome**.

If the account has several dehumidifiers, the integration asks which one to add. Set up the integration again for each of the others.

## Use a separate Midea account

Create a second account in the Midea app and share the dehumidifier to it from your main account, then give Home Assistant the second account:

- Home Assistant never competes with your phone for the account's limited login slots.
- Your main password stays out of Home Assistant.
- Removing the share revokes Home Assistant's access.

## Password storage

The integration doesn't store your password. The Midea login sends hashes of the password combined with a login ID that the cloud issues fresh for every login, so the integration stores only the parts that depend on the password: its SHA-256 hash and its double MD5 hash. At each login it combines them with the new login ID, exactly as the Midea app does with the password.

These stored hashes have limits:

- They let anyone who has them log in to that Midea account, just like the password would.
- They aren't salted, because the Midea login format leaves no room for a salt, so a weak password could be recovered from them with precomputed tables. A long, random password can't.

Protect the account with a long, unique password; the separate account described above limits what a leak would expose.

The password must contain only plain ASCII characters (no accents or emoji), because that is all the Midea login hashing supports.

After changing the password in the Midea app, enter the new one under **Configure**. Entries set up with version 0.1.0, which stored the password, switch to hashes automatically the next time Home Assistant starts. Entries set up with version 0.2.0 or 0.2.1 stored hashes that only worked once: enter the password again under **Configure**.

## Polling

The integration polls the cloud every 5 minutes by default, which is plenty for humidity, since it changes slowly. You can change this under **Configure**. Changes you make from Home Assistant apply immediately, whatever the interval. Polling much more often puts load on Midea's servers for little benefit.

## How it works

The integration uses the [midea-beautiful-air](https://github.com/nbogojevic/midea-beautiful-air) library, which is no longer maintained and stopped working with the current Midea cloud. The integration works around this:

- **Login:** the library logs in with a device ID that all its users share, and the cloud now rejects it ("too many devices logged in", error 65027). The integration creates a random device ID and push token at setup and keeps using them, so Home Assistant always looks like the same phone.
- **Commands:** the cloud now rejects the fields the library sends to the appliance. The integration sends the request the way the cloud expects it (`applianceCode` and only the fields the cloud accepts).

A future change to the Midea cloud could stop the integration from working.

## License

This integration is licensed under the [GNU General Public License v3.0](LICENSE). It is not affiliated with or endorsed by Midea.
