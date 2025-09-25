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
    const { limit = 12, productId } = await req.json()
    
    const shopifyDomain = Deno.env.get('ShopifyDomain')
    const storefrontAccessToken = Deno.env.get('StorefrontAccessToken')

    if (!shopifyDomain || !storefrontAccessToken) {
      throw new Error('Shopify credentials not configured')
    }

    let query, variables

    if (productId) {
      // Single product query
      query = `
        query getProduct($id: ID!) {
          product(id: $id) {
            id
            title
            description
            descriptionHtml
            handle
            vendor
            productType
            tags
            featuredImage {
              url
              altText
            }
            variants(first: 10) {
              edges {
                node {
                  id
                  title
                  price {
                    amount
                    currencyCode
                  }
                  compareAtPrice {
                    amount
                    currencyCode
                  }
                  availableForSale
                  quantityAvailable
                  selectedOptions {
                    name
                    value
                  }
                }
              }
            }
            priceRange {
              minVariantPrice {
                amount
                currencyCode
              }
              maxVariantPrice {
                amount
                currencyCode
              }
            }
            availableForSale
          }
        }
      `
      variables = { id: productId }
    } else {
      // Multiple products query
      query = `
        query getProducts($first: Int!) {
          products(first: $first) {
            edges {
              node {
                id
                title
                description
                handle
                vendor
                productType
                tags
                featuredImage {
                  url
                  altText
                }
                variants(first: 1) {
                  edges {
                    node {
                      id
                      title
                      price {
                        amount
                        currencyCode
                      }
                      compareAtPrice {
                        amount
                        currencyCode
                      }
                      availableForSale
                      quantityAvailable
                    }
                  }
                }
                priceRange {
                  minVariantPrice {
                    amount
                    currencyCode
                  }
                }
                availableForSale
              }
            }
          }
        }
      `
      variables = { first: limit }
    }

    const response = await fetch(`https://${shopifyDomain}/api/2024-01/graphql.json`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Shopify-Storefront-Access-Token': storefrontAccessToken,
      },
      body: JSON.stringify({
        query,
        variables
      })
    })

    const data = await response.json()

    if (data.errors) {
      throw new Error(`Shopify API error: ${JSON.stringify(data.errors)}`)
    }

    if (productId) {
      return new Response(
        JSON.stringify(data.data.product),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    } else {
      const products = data.data.products.edges.map((edge: any) => edge.node)
      return new Response(
        JSON.stringify({ products }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

  } catch (error) {
    console.error('Error:', error)
    return new Response(
      JSON.stringify({ error: error.message }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
    )
  }
})