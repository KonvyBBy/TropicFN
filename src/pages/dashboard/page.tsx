
import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { supabase } from '../../lib/supabase'
import Header from '../../components/feature/Header'
import Footer from '../../components/feature/Footer'

interface Order {
  id: string
  order_id: string
  user_id: string | null
  product_name: string
  product_description: string
  price: number
  status: 'pending' | 'completed' | 'cancelled'
  created_by: string
  redeemed_at?: string
  created_at: string
  updated_at: string
}

interface ChatMessage {
  id: string
  conversation_id: string
  sender_id: string
  sender_username: string
  message: string
  is_admin: boolean
  created_at: string
}

interface ChatConversation {
  id: string
  user_id: string
  username: string
  admin_last_seen: string | null
  user_last_seen: string | null
  status: string
  created_at: string
  updated_at: string
}

export default function Dashboard() {
  const { user, logout } = useAuth()
  const [activeTab, setActiveTab] = useState('orders')
  const [orders, setOrders] = useState<Order[]>([])
  const [redeemCode, setRedeemCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [newMessage, setNewMessage] = useState('')
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [adminLastSeen, setAdminLastSeen] = useState<string | null>(null)

  useEffect(() => {
    if (user) {
      loadOrders()
      initializeChat()
    }
  }, [user])

  useEffect(() => {
    if (conversationId) {
      loadChatMessages()
      updateUserLastSeen()
    }
  }, [conversationId])

  const loadOrders = async () => {
    if (!user) return

    try {
      const { data, error } = await supabase
        .from('orders')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false })

      if (error) throw error
      setOrders(data || [])
    } catch (error) {
      console.error('Error loading orders:', error)
    }
  }

  const initializeChat = async () => {
    if (!user) return

    try {
      const { data: existingConversation, error: findError } = await supabase
        .from('chat_conversations')
        .select('*')
        .eq('user_id', user.id)
        .single()

      if (existingConversation) {
        setConversationId(existingConversation.id)
        setAdminLastSeen(existingConversation.admin_last_seen)
      } else {
        // Create new conversation
        const { data: newConversation, error: createError } = await supabase
          .from('chat_conversations')
          .insert([{
            user_id: user.id,
            username: user.username,
            admin_last_seen: null,
            user_last_seen: new Date().toISOString(),
            status: 'active'
          }])
          .select()
          .single()

        if (createError) {
          console.error('Create conversation error:', createError)
        } else if (newConversation) {
          setConversationId(newConversation.id)
        }
      }
    } catch (error) {
      console.error('Error initializing chat:', error)
    }
  }

  const loadChatMessages = async () => {
    if (!conversationId) return

    try {
      const { data, error } = await supabase
        .from('chat_messages')
        .select('*')
        .eq('conversation_id', conversationId)
        .order('created_at', { ascending: true })

      if (error) throw error
      setChatMessages(data || [])
    } catch (error) {
      console.error('Error loading messages:', error)
    }
  }

  const updateUserLastSeen = async () => {
    if (!conversationId) return

    try {
      await supabase
        .from('chat_conversations')
        .update({ user_last_seen: new Date().toISOString() })
        .eq('id', conversationId)
    } catch (error) {
      console.error('Error updating user last seen:', error)
    }
  }

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newMessage.trim() || !conversationId || !user) return

    try {
      const { error } = await supabase
        .from('chat_messages')
        .insert([{
          conversation_id: conversationId,
          sender_id: user.id,
          sender_username: user.username,
          message: newMessage.trim(),
          is_admin: false
        }])

      if (error) throw error

      // Update conversation timestamp
      await supabase
        .from('chat_conversations')
        .update({ 
          updated_at: new Date().toISOString(),
          user_last_seen: new Date().toISOString()
        })
        .eq('id', conversationId)

      setNewMessage('')
      loadChatMessages()
    } catch (error) {
      console.error('Error sending message:', error)
    }
  }

  const getTimeSince = (dateString: string) => {
    const now = new Date()
    const date = new Date(dateString)
    const diffInMinutes = Math.floor((now.getTime() - date.getTime()) / (1000 * 60))
    
    if (diffInMinutes < 1) return 'Just now'
    if (diffInMinutes < 60) return `${diffInMinutes}m ago`
    if (diffInMinutes < 1440) return `${Math.floor(diffInMinutes / 60)}h ago`
    return `${Math.floor(diffInMinutes / 1440)}d ago`
  }

  const handleRedeem = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!user || !redeemCode.trim()) return

    setLoading(true)
    setMessage('')

    try {
      // Submit to Google Forms for tracking
      const formData = new FormData()
      formData.append('username', user.username)
      formData.append('user_email', user.email)
      formData.append('order_id', redeemCode.trim().toUpperCase())
      formData.append('redemption_date', new Date().toISOString())
      formData.append('status', 'redeemed')

      const response = await fetch('https://readdy.ai/api/form/d3a9fvog1baue90asg80', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams(formData as any).toString()
      })

      if (response.ok) {
        setMessage('Order submitted successfully! We will process your redemption request.')
        setRedeemCode('')
        
        // Add to database for immediate display
        const { error } = await supabase
          .from('orders')
          .insert([{
            order_id: redeemCode.trim().toUpperCase(),
            user_id: user.id,
            product_name: 'Fortnite Account',
            product_description: 'Premium Fortnite Account with Skins',
            price: 0,
            status: 'pending',
            created_by: 'system'
          }])

        if (!error) {
          loadOrders() // Refresh orders list
        }
      } else {
        setMessage('Failed to submit order. Please try again.')
      }
    } catch (error) {
      console.error('Error submitting order:', error)
      setMessage('Failed to submit order. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Access Denied</h1>
          <p className="text-gray-600">Please log in to access your dashboard.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-white rounded-xl shadow-sm">
          <div className="border-b border-gray-200 px-6 py-4">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">Welcome, {user.username}!</h1>
                <p className="text-gray-600 mt-1">Manage your account and orders</p>
              </div>
              <button
                onClick={logout}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors whitespace-nowrap"
              >
                <i className="ri-logout-box-line mr-2"></i>
                Sign Out
              </button>
            </div>
          </div>

          <div className="flex">
            {/* Sidebar */}
            <div className="w-64 border-r border-gray-200 p-6">
              <nav className="space-y-2">
                <button
                  onClick={() => setActiveTab('orders')}
                  className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors whitespace-nowrap ${
                    activeTab === 'orders'
                      ? 'bg-blue-50 text-blue-700 border border-blue-200'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <i className="ri-shopping-bag-line mr-3"></i>
                  My Orders
                </button>
                <button
                  onClick={() => setActiveTab('redeem')}
                  className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors whitespace-nowrap ${
                    activeTab === 'redeem'
                      ? 'bg-blue-50 text-blue-700 border border-blue-200'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <i className="ri-gift-line mr-3"></i>
                  Redeem Order
                </button>
                <button
                  onClick={() => setActiveTab('messages')}
                  className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors whitespace-nowrap ${
                    activeTab === 'messages'
                      ? 'bg-blue-50 text-blue-700 border border-blue-200'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <i className="ri-message-3-line mr-3"></i>
                  Message Admin
                </button>
                <button
                  onClick={() => setActiveTab('profile')}
                  className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors whitespace-nowrap ${
                    activeTab === 'profile'
                      ? 'bg-blue-50 text-blue-700 border border-blue-200'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <i className="ri-user-line mr-3"></i>
                  Profile Settings
                </button>
              </nav>
            </div>

            {/* Main Content */}
            <div className="flex-1 p-6">
              {activeTab === 'orders' && (
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 mb-6">My Orders</h2>
                  {orders.length === 0 ? (
                    <div className="text-center py-12">
                      <i className="ri-shopping-bag-line text-4xl text-gray-400 mb-4"></i>
                      <h3 className="text-lg font-medium text-gray-900 mb-2">No orders yet</h3>
                      <p className="text-gray-600">Your redeemed orders will appear here.</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {orders.map((order) => (
                        <div key={order.id} className="border border-gray-200 rounded-lg p-6 bg-white">
                          <div className="flex items-center justify-between mb-4">
                            <div>
                              <h3 className="font-semibold text-gray-900 text-lg">{order.product_name}</h3>
                              <p className="text-sm text-gray-600 font-mono bg-gray-100 px-3 py-1 rounded-md inline-block mt-2">
                                Order ID: {order.order_id}
                              </p>
                            </div>
                            <div className="text-right">
                              <span className={`inline-flex px-3 py-1 rounded-full text-xs font-medium ${
                                order.status === 'completed' 
                                  ? 'bg-green-100 text-green-800'
                                  : order.status === 'pending'
                                  ? 'bg-yellow-100 text-yellow-800'
                                  : 'bg-red-100 text-red-800'
                              }`}>
                                {order.status.charAt(0).toUpperCase() + order.status.slice(1)}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center justify-between text-sm text-gray-500 border-t pt-3">
                            <span>Order Created: {new Date(order.created_at).toLocaleDateString()}</span>
                            {order.redeemed_at && (
                              <span>Redeemed: {new Date(order.redeemed_at).toLocaleDateString()}</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'redeem' && (
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 mb-6">Redeem Order</h2>
                  <div className="max-w-md">
                    <form onSubmit={handleRedeem} data-readdy-form id="order-redeem-form">
                      <div className="mb-4">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Order ID
                        </label>
                        <input
                          type="text"
                          name="order_id"
                          value={redeemCode}
                          onChange={(e) => setRedeemCode(e.target.value)}
                          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 bg-white font-mono"
                          placeholder="Enter your order ID"
                          required
                        />
                      </div>
                      
                      {message && (
                        <div className={`mb-4 p-3 rounded-lg ${
                          message.includes('successfully') 
                            ? 'bg-green-50 text-green-700 border border-green-200'
                            : 'bg-red-50 text-red-700 border border-red-200'
                        }`}>
                          {message}
                        </div>
                      )}

                      <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors disabled:opacity-50 whitespace-nowrap"
                      >
                        {loading ? 'Submitting...' : 'Submit Order'}
                      </button>
                    </form>
                    
                    <div className="mt-6 p-4 bg-blue-50 rounded-lg">
                      <h3 className="font-medium text-blue-900 mb-2">How it works:</h3>
                      <ol className="text-sm text-blue-800 space-y-1">
                        <li>1. Enter the order ID provided by Konvy</li>
                        <li>2. Click "Submit Order" to send for processing</li>
                        <li>3. We'll track your submission via Google Forms</li>
                        <li>4. Admin will process and fulfill your order</li>
                      </ol>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'messages' && (
                <div className="flex flex-col h-[600px] bg-white rounded-lg border border-gray-200">
                  <div className="p-4 border-b border-gray-200">
                    <div className="flex items-center justify-between">
                      <div>
                        <h2 className="text-lg font-semibold text-gray-900">Message Admin</h2>
                        <p className="text-sm text-gray-600">Get help and support from Konvy</p>
                      </div>
                      <div className="text-right">
                        <div className="flex items-center">
                          <div className={`w-2 h-2 rounded-full mr-2 ${
                            adminLastSeen && new Date().getTime() - new Date(adminLastSeen).getTime() < 300000 
                              ? 'bg-green-500' 
                              : 'bg-gray-400'
                          }`}></div>
                          <span className="text-sm text-gray-600">
                            Admin last seen: {adminLastSeen ? getTimeSince(adminLastSeen) : 'Never'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {chatMessages.length === 0 ? (
                      <div className="text-center py-12">
                        <i className="ri-chat-3-line text-4xl text-gray-400 mb-4"></i>
                        <h3 className="text-lg font-medium text-gray-900 mb-2">Start a conversation</h3>
                        <p className="text-gray-600">Send a message to get help from the admin</p>
                      </div>
                    ) : (
                      chatMessages.map((msg) => (
                        <div
                          key={msg.id}
                          className={`flex ${msg.is_admin ? 'justify-start' : 'justify-end'}`}
                        >
                          <div className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                            msg.is_admin
                              ? 'bg-gray-100 text-black border border-gray-200'
                              : 'bg-blue-600 text-white'
                          }`}>
                            <p className="text-sm font-medium mb-1">
                              {msg.is_admin ? 'Admin' : 'You'}
                            </p>
                            <p className="break-words">{msg.message}</p>
                            <p className={`text-xs mt-1 ${
                              msg.is_admin ? 'text-gray-500' : 'text-blue-100'
                            }`}>
                              {new Date(msg.created_at).toLocaleTimeString()}
                            </p>
                          </div>
                        </div>
                      ))
                    )}
                  </div>

                  <div className="p-4 border-t border-gray-200">
                    <form onSubmit={sendMessage} className="flex gap-2">
                      <input
                        type="text"
                        value={newMessage}
                        onChange={(e) => setNewMessage(e.target.value)}
                        className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 bg-white"
                        placeholder="Type your message..."
                        required
                      />
                      <button
                        type="submit"
                        className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors whitespace-nowrap"
                      >
                        <i className="ri-send-plane-line"></i>
                      </button>
                    </form>
                  </div>
                </div>
              )}

              {activeTab === 'profile' && (
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 mb-6">Profile Settings</h2>
                  <div className="max-w-2xl space-y-6">
                    <div className="bg-white border border-gray-200 rounded-lg p-6">
                      <h3 className="font-semibold text-gray-900 mb-4">Account Information</h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-2">Username</label>
                          <input
                            type="text"
                            value={user.username}
                            className="w-full px-4 py-3 border border-gray-300 rounded-lg bg-gray-50 text-gray-900"
                            disabled
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-2">Email</label>
                          <input
                            type="email"
                            value={user.email}
                            className="w-full px-4 py-3 border border-gray-300 rounded-lg bg-gray-50 text-gray-900"
                            disabled
                          />
                        </div>
                      </div>
                    </div>

                    <div className="bg-white border border-gray-200 rounded-lg p-6">
                      <h3 className="font-semibold text-gray-900 mb-4">Security Settings</h3>
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <h4 className="font-medium text-gray-900">Two-Factor Authentication</h4>
                            <p className="text-sm text-gray-600">Add an extra layer of security to your account</p>
                          </div>
                          <button className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 transition-colors whitespace-nowrap">
                            Enable 2FA
                          </button>
                        </div>
                        <div className="border-t pt-4">
                          <button className="bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors whitespace-nowrap">
                            Change Password
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <Footer />
    </div>
  )
}
