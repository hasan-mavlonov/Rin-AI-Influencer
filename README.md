# Rin AI Influencer

This project automates the generation and publishing of Instagram content for the Rin persona. Posting is now handled via the Instagram Graph API, which means no browser automation is required on production runs.

## Instagram configuration

Create an Instagram Business or Creator account connected to a Facebook Page, then generate a permanent user access token that has the `instagram_basic`, `pages_show_list`, and `instagram_content_publish` permissions. Store the following keys inside your `.env` file:

```
INSTAGRAM_ACCESS_TOKEN=EAAG...
INSTAGRAM_BUSINESS_ACCOUNT_ID=1784...
```

With those credentials in place, `poster/instagram_poster.py` will upload images directly through the Graph API and publish them to the @main account that the Business ID belongs to.
