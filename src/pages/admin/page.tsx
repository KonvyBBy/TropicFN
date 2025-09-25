
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

interface User {
  id: string
  email: string
  username: string
  role: 'customer' | 'owner'
  two_factor_enabled: boolean
  last_active: string
  is_online: boolean
  created_at: string
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

export default function AdminDashboard() {
  const { user, adminLogin, logout } = useAuth()
  const [activeTab, setActiveTab] = useState('orders')
  const [orders, setOrders] = useState<Order[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(false)
  const [showAdminLogin, setShowAdminLogin] = useState(false)
  const [adminPassword, setAdminPassword] = useState('')
  const [adminError, setAdminError] = useState('')
  const [conversations, setConversations] = useState<ChatConversation[]>([])
  const [selectedConversation, setSelectedConversation] = useState<string | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [newMessage, setNewMessage] = useState('')
  const [createMessage, setCreateMessage] = useState('')
  const [newOrder, setNewOrder] = useState({
    product_name: '',
    order_id: ''
  })

  useEffect(() => {
    if (user?.role === 'owner') {
      loadOrders()
      loadUsers()
      loadConversations()
    } else {
      setShowAdminLogin(true)
    }
  }, [user])

  useEffect(() => {
    if (selectedConversation) {
      loadChatMessages(selectedConversation)
      updateAdminLastSeen(selectedConversation)
    }
  }, [selectedConversation])

  const handleAdminLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setAdminError('')
    setLoading(true)

    try {
      const result = await adminLogin(adminPassword)
      if (result.success) {
        setShowAdminLogin(false)
        setAdminPassword('')
      } else {
        setAdminError(result.error || 'Login failed')
      }
    } catch (error) {
      setAdminError('Login failed')
    } finally {
      setLoading(false)
    }
  }

  const loadOrders = async () => {
    try {
      const { data, error } = await supabase
        .from('orders')
        .select('*')
        .order('created_at', { ascending: false })

      if (error) throw error
      setOrders(data || [])
    } catch (error) {
      console.error('Error loading orders:', error)
    }
  }

  const loadUsers = async () => {
    try {
      const { data, error } = await supabase
        .from('users')
        .select('*')
        .neq('role', 'owner')
        .order('created_at', { ascending: false })

      if (error) throw error
      setUsers(data || [])
    } catch (error) {
      console.error('Error loading users:', error)
    }
  }

  const loadConversations = async () => {
    try {
      const { data, error } = await supabase
        .from('chat_conversations')
        .select('*')
        .order('updated_at', { ascending: false })

      if (error) throw error
      setConversations(data || [])
    } catch (error) {
      console.error('Error loading conversations:', error)
    }
  }

  const loadChatMessages = async (conversationId: string) => {
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

  const updateAdminLastSeen = async (conversationId: string) => {
    try {
      await supabase
        .from('chat_conversations')
        .update({ admin_last_seen: new Date().toISOString() })
        .eq('id', conversationId)

      // Update local state
      setConversations(prev => prev.map(conv => 
        conv.id === conversationId 
          ? { ...conv, admin_last_seen: new Date().toISOString() }
          : conv
      ))
    } catch (error) {
      console.error('Error updating admin last seen:', error)
    }
  }

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newMessage.trim() || !selectedConversation || !user) return

    try {
      const { error } = await supabase
        .from('chat_messages')
        .insert([{
          conversation_id: selectedConversation,
          sender_id: user.id,
          sender_username: user.username,
          message: newMessage.trim(),
          is_admin: true
        }])

      if (error) throw error

      // Update conversation timestamp
      await supabase
        .from('chat_conversations')
        .update({ 
          updated_at: new Date().toISOString(),
          admin_last_seen: new Date().toISOString()
        })
        .eq('id', selectedConversation)

      setNewMessage('')
      loadChatMessages(selectedConversation)
      loadConversations()
    } catch (error) {
      console.error('Error sending message:', error)
    }
  }

  const generateOrderId = () => {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    let result = ''
    for (let i = 0; i < 8; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length))
    }
    setNewOrder({ ...newOrder, order_id: result })
  }

  const createOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!user || !newOrder.product_name.trim() || !newOrder.order_id.trim()) {
      setCreateMessage('Please fill in all fields')
      return
    }

    setLoading(true)
    setCreateMessage('')
    
    try {
      // Check if order_id already exists
      const { data: existingOrder } = await supabase
        .from('orders')
        .select('order_id')
        .eq('order_id', newOrder.order_id.trim().toUpperCase())
        .single()

      if (existingOrder) {
        setCreateMessage('Order ID already exists. Please use a different ID.')
        setLoading(false)
        return
      }

      // Create the new order
      const { error } = await supabase
        .from('orders')
        .insert([{
          order_id: newOrder.order_id.trim().toUpperCase(),
          product_name: newOrder.product_name.trim(),
          product_description: '',
          price: 0,
          created_by: user.id,
          status: 'pending',
          user_id: null
        }])

      if (error) throw error

      setCreateMessage('Order created successfully!')
      setNewOrder({ product_name: '', order_id: '' })
      loadOrders()
    } catch (error) {
      console.error('Error creating order:', error)
      setCreateMessage('Failed to create order. Please try again.')
    } finally {
      setLoading(false)
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

  // Admin Login Modal
  if (showAdminLogin) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl p-8 max-w-md w-full shadow-xl">
          <div className="text-center mb-6">
            <div className="w-16 h-16 bg-blue-600 rounded-full flex items-center justify-center mx-auto mb-4">
              <i className="ri-shield-keyhole-line text-white text-2xl"></i>
            </div>
            <h2 className="text-2xl font-bold text-gray-900">Admin Access</h2>
            <p className="text-gray-600 mt-2">Enter the admin password to continue</p>
          </div>

          {adminError && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
              {adminError}
            </div>
          )}

          <form onSubmit={handleAdminLogin}>
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Admin Password
              </label>
              <input
                type="password"
                value={adminPassword}
                onChange={(e) => setAdminPassword(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 bg-white"
                placeholder="Enter admin password"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors disabled:opacity-50 whitespace-nowrap"
            >
              {loading ? 'Verifying...' : 'Access Admin Panel'}
            </button>
          </form>

          <div className="mt-6 text-center">
            <button
              onClick={() => window.history.back()}
              className="text-gray-600 hover:text-gray-800 font-medium"
            >
              ← Go Back
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!user || user.role !== 'owner') {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Access Denied</h1>
          <p className="text-gray-600">Only the owner can access this dashboard.</p>
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
                <h1 className="text-2xl font-bold text-gray-900">Konvy Admin Dashboard</h1>
                <p className="text-gray-600 mt-1">Welcome back, {user.username}! Manage your orders and users.</p>
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
                  All Orders
                </button>
                <button
                  onClick={() => setActiveTab('create')}
                  className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors whitespace-nowrap ${
                    activeTab === 'create'
                      ? 'bg-blue-50 text-blue-700 border border-blue-200'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <i className="ri-add-circle-line mr-3"></i>
                  Create Order
                </button>
                <button
                  onClick={() => setActiveTab('users')}
                  className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors whitespace-nowrap ${
                    activeTab === 'users'
                      ? 'bg-blue-50 text-blue-700 border border-blue-200'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <i className="ri-team-line mr-3"></i>
                  Users ({users.length})
                </button>
                <button
                  onClick={() => {
                    setActiveTab('messages')
                    loadConversations()
                  }}
                  className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors whitespace-nowrap ${
                    activeTab === 'messages'
                      ? 'bg-blue-50 text-blue-700 border border-blue-200'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <i className="ri-message-3-line mr-3"></i>
                  User Messages ({conversations.length})
                </button>
              </nav>
            </div>

            {/* Main Content */}
            <div className="flex-1 p-6">
              {/* Orders Tab */}
              {activeTab === 'orders' && (
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 mb-6">All Orders</h2>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
                      <div className="flex items-center">
                        <div className="w-12 h-12 bg-blue-600 rounded-lg flex items-center justify-center">
                          <i className="ri-shopping-bag-line text-white text-xl"></i>
                        </div>
                        <div className="ml-4">
                          <p className="text-sm font-medium text-blue-600">Total Orders</p>
                          <p className="text-2xl font-bold text-blue-900">{orders.length}</p>
                        </div>
                      </div>
                    </div>

                    <div className="bg-green-50 border border-green-200 rounded-lg p-6">
                      <div className="flex items-center">
                        <div className="w-12 h-12 bg-green-600 rounded-lg flex items-center justify-center">
                          <i className="ri-check-line text-white text-xl"></i>
                        </div>
                        <div className="ml-4">
                          <p className="text-sm font-medium text-green-600">Redeemed</p>
                          <p className="text-2xl font-bold text-green-900">
                            {orders.filter(o => o.status === 'completed').length}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
                      <div className="flex items-center">
                        <div className="w-12 h-12 bg-yellow-600 rounded-lg flex items-center justify-center">
                          <i className="ri-time-line text-white text-xl"></i>
                        </div>
                        <div className="ml-4">
                          <p className="text-sm font-medium text-yellow-600">Pending Redemption</p>
                          <p className="text-2xl font-bold text-yellow-900">
                            {orders.filter(o => o.status === 'pending').length}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    {orders.length === 0 ? (
                      <div className="text-center py-12">
                        <i className="ri-shopping-bag-line text-4xl text-gray-400 mb-4"></i>
                        <h3 className="text-lg font-medium text-gray-900 mb-2">No orders yet</h3>
                        <p className="text-gray-600">Create your first order to get started.</p>
                      </div>
                    ) : (
                      orders.map((order) => (
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
                                {order.status === 'completed' ? 'Redeemed' : 'Pending Redemption'}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center justify-between text-sm text-gray-500 border-t pt-3">
                            <span>Created: {new Date(order.created_at).toLocaleDateString()}</span>
                            {order.redeemed_at && (
                              <span>Redeemed: {new Date(order.redeemed_at).toLocaleDateString()}</span>
                            )}
                            {order.user_id ? (
                              <span className="text-green-600 font-medium">✓ Redeemed by customer</span>
                            ) : (
                              <span className="text-yellow-600 font-medium">⏳ Awaiting redemption</span>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              {/* Create Order Tab */}
              {activeTab === 'create' && (
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 mb-6">Create New Order</h2>
                  <div className="max-w-2xl">
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                      <div className="flex items-start">
                        <i className="ri-information-line text-blue-600 text-xl mt-0.5 mr-3"></i>
                        <div>
                          <h3 className="font-medium text-blue-900 mb-1">How it works:</h3>
                          <p className="text-sm text-blue-800">Create an order with a unique Order ID and product name. Customers can redeem this order using the Order ID you provide them.</p>
                        </div>
                      </div>
                    </div>

                    <form onSubmit={createOrder} className="bg-white border border-gray-200 rounded-lg p-6">
                      <div className="mb-6">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Product Name *
                        </label>
                        <input
                          type="text"
                          value={newOrder.product_name}
                          onChange={(e) => setNewOrder({ ...newOrder, product_name: e.target.value })}
                          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 bg-white"
                          placeholder="e.g., Fortnite Rare Account, Gaming Setup, etc."
                          required
                        />
                      </div>

                      <div className="mb-6">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Order ID *
                        </label>
                        <div className="flex gap-3">
                          <input
                            type="text"
                            value={newOrder.order_id}
                            onChange={(e) => setNewOrder({ ...newOrder, order_id: e.target.value.toUpperCase() })}
                            className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 bg-white font-mono"
                            placeholder="Enter unique order ID"
                            required
                          />
                          <button
                            type="button"
                            onClick={generateOrderId}
                            className="px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors whitespace-nowrap"
                          >
                            <i className="ri-refresh-line mr-2"></i>
                            Generate
                          </button>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">This is the ID customers will use to redeem their order</p>
                      </div>

                      {createMessage && (
                        <div className={`mb-4 p-3 rounded-lg ${
                          createMessage.includes('successfully') 
                            ? 'bg-green-50 text-green-700 border border-green-200'
                            : 'bg-red-50 text-red-700 border border-red-200'
                        }`}>
                          {createMessage}
                        </div>
                      )}

                      <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors disabled:opacity-50 whitespace-nowrap"
                      >
                        {loading ? 'Creating Order...' : 'Create Order'}
                      </button>
                    </form>
                  </div>
                </div>
              )}

              {/* Users Tab */}
              {activeTab === 'users' && (
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 mb-6">Registered Users</h2>
                  <div className="space-y-4">
                    {users.length === 0 ? (
                      <div className="text-center py-12">
                        <i className="ri-team-line text-4xl text-gray-400 mb-4"></i>
                        <h3 className="text-lg font-medium text-gray-900 mb-2">No users yet</h3>
                        <p className="text-gray-600">User registrations will appear here.</p>
                      </div>
                    ) : (
                      users.map((userData) => (
                        <div key={userData.id} className="border border-gray-200 rounded-lg p-6 bg-white">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center">
                              <div className="w-12 h-12 bg-blue-600 rounded-full flex items-center justify-center">
                                <i className="ri-user-line text-white text-xl"></i>
                              </div>
                              <div className="ml-4">
                                <h3 className="font-semibold text-gray-900">{userData.username}</h3>
                                <p className="text-sm text-gray-600">{userData.email}</p>
                              </div>
                            </div>
                            <div className="text-right">
                              <div className="flex items-center">
                                <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium mr-3 ${
                                  userData.is_online 
                                    ? 'bg-green-100 text-green-800'
                                    : 'bg-gray-100 text-gray-800'
                                }`}>
                                  {userData.is_online ? 'Online' : 'Offline'}
                                </span>
                                <div className="text-sm text-gray-500">
                                  Last active: {new Date(userData.last_active).toLocaleDateString()}
                                </div>
                              </div>
                              <div className="text-sm text-gray-500 mt-1">
                                Joined: {new Date(userData.created_at).toLocaleDateString()}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              {/* Messages Tab */}
              {activeTab === 'messages' && (
                <div className="flex h-[600px]">
                  {/* Conversations List */}
                  <div className="w-1/3 border-r border-gray-200 bg-white">
                    <div className="p-4 border-b border-gray-200">
                      <h2 className="text-lg font-semibold text-gray-900">User Messages</h2>
                      <p className="text-sm text-gray-600">Click on a conversation to reply</p>
                    </div>
                    <div className="overflow-y-auto h-full">
                      {conversations.length === 0 ? (
                        <div className="p-6 text-center">
                          <i className="ri-message-3-line text-3xl text-gray-400 mb-3"></i>
                          <p className="text-gray-600">No messages yet</p>
                          <p className="text-sm text-gray-500">User messages will appear here</p>
                        </div>
                      ) : (
                        conversations.map((conversation) => (
                          <div
                            key={conversation.id}
                            onClick={() => setSelectedConversation(conversation.id)}
                            className={`p-4 border-b border-gray-100 cursor-pointer hover:bg-gray-50 ${
                              selectedConversation === conversation.id ? 'bg-blue-50 border-blue-200' : ''
                            }`}
                          >
                            <div className="flex items-center justify-between mb-2">
                              <h3 className="font-medium text-gray-900">{conversation.username}</h3>
                              <span className="text-xs text-gray-500">
                                {getTimeSince(conversation.updated_at)}
                              </span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-sm text-gray-600">
                                User last seen: {conversation.user_last_seen ? getTimeSince(conversation.user_last_seen) : 'Never'}
                              </span>
                              {!conversation.admin_last_seen && (
                                <div className="w-2 h-2 bg-blue-600 rounded-full"></div>
                              )}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Chat Messages */}
                  <div className="flex-1 flex flex-col bg-white">
                    {selectedConversation ? (
                      <>
                        <div className="p-4 border-b border-gray-200">
                          <h3 className="font-semibold text-gray-900">
                            Conversation with {conversations.find(c => c.id === selectedConversation)?.username}
                          </h3>
                          <p className="text-sm text-gray-600">
                            User last seen: {conversations.find(c => c.id === selectedConversation)?.user_last_seen 
                              ? getTimeSince(conversations.find(c => c.id === selectedConversation)!.user_last_seen!) 
                              : 'Never'}
                          </p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-4 space-y-3">
                          {chatMessages.length === 0 ? (
                            <div className="text-center py-12">
                              <i className="ri-chat-3-line text-4xl text-gray-400 mb-4"></i>
                              <h3 className="text-lg font-medium text-gray-900 mb-2">No messages yet</h3>
                              <p className="text-gray-600">This user hasn't sent any messages</p>
                            </div>
                          ) : (
                            chatMessages.map((message) => (
                              <div
                                key={message.id}
                                className={`flex ${message.is_admin ? 'justify-end' : 'justify-start'}`}
                              >
                                <div className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                                  message.is_admin
                                    ? 'bg-blue-600 text-white'
                                    : 'bg-gray-100 text-black border border-gray-200'
                                }`}>
                                  <p className="text-sm font-medium mb-1">
                                    {message.is_admin ? 'Admin' : message.sender_username}
                                  </p>
                                  <p className="break-words">{message.message}</p>
                                  <p className={`text-xs mt-1 ${
                                    message.is_admin ? 'text-blue-100' : 'text-gray-500'
                                  }`}>
                                    {new Date(message.created_at).toLocaleTimeString()}
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
                              placeholder="Reply to user..."
                              required
                            />
                            <button
                              type="submit"
                              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors whitespace-nowrap"
                            >
                              Send
                            </button>
                          </form>
                        </div>
                      </>
                    ) : (
                      <div className="flex-1 flex items-center justify-center">
                        <div className="text-center">
                          <i className="ri-chat-3-line text-4xl text-gray-400 mb-4"></i>
                          <h3 className="text-lg font-medium text-gray-900 mb-2">Select a conversation</h3>
                          <p className="text-gray-600">Choose a user from the left to view their messages</p>
                        </div>
                      </div>
                    )}
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
