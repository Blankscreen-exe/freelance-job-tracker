- **DONE** minio for profile picture and other asset support
- payment gateway integration for payment support
- email engine support, admin notifications, middleman emails, client emails(invoice notification), worker emails (payment notification)
- **DONE** as an admin i should be able to create users with only "worker" or "middleman" role, i should also be able to change roles for any existing user
- user listing should be of 2 types: clients and other types of users

- **DONE** workers should not see the clients list. they only see the following:
    - jobs (only which they are in)
    - other user's list (excluding clients)
    - payments (only history of those made to them)
    - dashboard ( only their details)

- **DONE** middlemen should only see:
    - dashboard ( only their details)
    - jobs (which they bring)
    - client list (which they bring)
    - payments (which are managed by them) to workers and cut to themselves
    - p&l report and ledger (only about themselves)
    - other users

- clients information will be stored in separate db tables. one for basic client details, one for their company details, one for their contact information etc
- expose minio on a new domain tracker-minio.dev-in-trenches.com

- make the app custommizable for the admin
    - primary color setting will be shown whereever there is a primary color
    - app name, shown in the title and everywhere it is required can be replaced with a logo image of specific size
    - custom favicon
    - what else can we do?

- light theme should show a dark color in the sidebar and the top navbar. similarly dark theme should show a slightly lighter sidebar and navbar