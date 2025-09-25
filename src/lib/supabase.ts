import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_PUBLIC_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_PUBLIC_SUPABASE_ANON_KEY

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

export interface User {
  id: string
  email: string
  username: string
  role: 'customer' | 'owner'
  two_factor_enabled: boolean
  last_active: string
  is_online: boolean
  created_at: string
}

export interface Order {
  id: string
  order_id: string
  user_id: string
  product_name: string
  product_description: string
  price: number
  status: 'pending' | 'completed' | 'cancelled'
  created_by: string
  redeemed_at?: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  sender_id: string
  recipient_id: string
  content: string
  is_read: boolean
  created_at: string
}