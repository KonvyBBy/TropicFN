import { serve } from "https://deno.land/std@0.168.0/http/server.ts"

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const { variantId, quantity = 1 } = await req.json()
    
    const shopifyDomain = Deno.env.get('ShopifyDomain')
    const storefrontAccessToken = Deno.env.get('StorefrontAccessToken')

    if (!shopifyDomain || !storefrontAccessToken) {
      throw new Error('Shopify credentials not configured')
    }

    // Create cart with the product
    const createCartMutation = `
      mutation cartCreate($input: CartInput!) {
        cartCreate(input: $input) {
          cart {
            id
            checkoutUrl
            estimatedCost {
              totalAmount {
                amount
                currencyCode
              }
            }
            lines(first: 100) {
              edges {
                node {
                  id
                  quantity
                  estimatedCost {
                    totalAmount {
                      amount
                      currencyCode
                    }
                  }
                  merchandise {
                    ... on ProductVariant {
                      id
                      title
                      product {
                        id
                        title
                        handle
                      }
                    }
                  }
                }
              }
            }
          }
          userErrors {
            field
            message
          }
        }
      }
    `

    const cartInput = {
      lines: [
        {
          merchandiseId: variantId,
          quantity: quantity
        }
      ]
    }

    const response = await fetch(`https://${shopifyDomain}/api/2024-01/graphql.json`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Shopify-Storefront-Access-Token': storefrontAccessToken,
      },
      body: JSON.stringify({
        query: createCartMutation,
        variables: { input: cartInput }
      })
    })

    const data = await response.json()

    if (data.errors) {
      throw new Error(`Shopify API error: ${JSON.stringify(data.errors)}`)
    }

    if (data.data.cartCreate.userErrors.length > 0) {
      throw new Error(`Cart creation error: ${JSON.stringify(data.data.cartCreate.userErrors)}`)
    }

    return new Response(
      JSON.stringify({
        success: true,
        cart: data.data.cartCreate.cart,
        checkoutUrl: data.data.cartCreate.cart.checkoutUrl
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('Error:', error)
    return new Response(
      JSON.stringify({ error: error.message }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
    )
  }
})