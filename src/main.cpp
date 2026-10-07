#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace fs=std::filesystem;
using I=std::int64_t;
struct Order {char side;I price,qty;};
bool read_line(std::istream& input,std::string& line){
    line.clear();char c=0;
    while(input.get(c)){
        if(c=='\n')return true;
        if(line.size()>=256)throw std::runtime_error("Row byte budget exceeded");
        line.push_back(c);
    }
    if(input.bad())throw std::runtime_error("Input read failed");
    return !line.empty();
}
I integer(const std::string& text){
    I n=0;auto [end,error]=std::from_chars(text.data(),text.data()+text.size(),n);
    if(error!=std::errc{}||end!=text.data()+text.size()||text.empty())throw std::runtime_error("Invalid integer");
    return n;
}
std::vector<std::string> split(const std::string& line){
    std::vector<std::string> fields;std::size_t start=0;
    for(std::size_t i=0;i<=line.size();++i)if(i==line.size()||line[i]==','){fields.push_back(line.substr(start,i-start));start=i+1;}
    if(fields.size()!=7)throw std::runtime_error("Expected 7 CSV fields; quoted CSV is not supported");
    return fields;
}
class Book {
    std::unordered_map<I,Order> orders;
    std::map<I,I,std::greater<I>> bids;
    std::map<I,I> asks;
    template<class Levels> static void reduce(Levels& levels,I price,I qty){auto found=levels.find(price);if(found==levels.end()||found->second<qty)throw std::runtime_error("Internal level invariant");found->second-=qty;if(found->second==0)levels.erase(found);}
    template<class Levels> static I top5(const Levels& levels){I total=0;int count=0;for(const auto& [price,qty]:levels){(void)price;if(count++==5)break;total+=qty;}return total;}
public:
    void apply(char action,I id,char side,I price,I qty){
        if(id<=0)throw std::runtime_error("Order ID must be positive");
        if(action=='A'){
            if(side!='B'&&side!='S')throw std::runtime_error("Add side must be B or S");
            if(price<=0||price>1000000000||qty<=0||qty>1000000000)throw std::runtime_error("Price/quantity outside 1..1e9");
            if(orders.contains(id))throw std::runtime_error("Duplicate live order ID");
            if(orders.size()>=1000000)throw std::runtime_error("Open order budget exceeded");
            if((side=='B'&&!asks.empty()&&price>=asks.begin()->first)||(side=='S'&&!bids.empty()&&price<=bids.begin()->first))throw std::runtime_error("Crossed book: execute trades before resting adds");
            if(side=='B')bids[price]+=qty;else asks[price]+=qty;
            orders.emplace(id,Order{side,price,qty});
        }else if(action=='C'||action=='T'){
            auto found=orders.find(id);if(found==orders.end())throw std::runtime_error("Unknown live order ID");
            Order& order=found->second;I amount=qty;
            if(action=='C'){
                if(side!='N'||price!=0||qty!=0)throw std::runtime_error("Cancel requires N,0,0");
                amount=order.qty;
            }else{
                if(side!=order.side||price!=order.price||qty<=0||qty>order.qty)throw std::runtime_error("Invalid maker execution");
                const I best=order.side=='B'?bids.begin()->first:asks.begin()->first;
                if(price!=best)throw std::runtime_error("Maker execution must use best resting price");
            }
            if(order.side=='B')reduce(bids,order.price,amount);else reduce(asks,order.price,amount);
            order.qty-=amount;if(order.qty==0)orders.erase(found);
        }else throw std::runtime_error("Unsupported action; expected A/C/T");
    }
    void snapshot(std::ostream& out,I seq,I time)const{
        auto bid=bids.empty()?0:bids.begin()->first,ask=asks.empty()?0:asks.begin()->first;
        auto bqty=bids.empty()?0:bids.begin()->second,aqty=asks.empty()?0:asks.begin()->second;
        out<<seq<<','<<time<<','<<bid<<','<<ask<<','<<bqty<<','<<aqty<<','<<top5(bids)<<','<<top5(asks)<<','<<orders.size()<<'\n';
    }
};
struct Temporary{fs::path path;~Temporary(){std::error_code ec;fs::remove(path,ec);}};
int main(int argc,char** argv){
    try{
        if(argc!=3)throw std::runtime_error("Usage: depthreplay events.csv NEW_snapshots.csv");
        const fs::path input=argv[1],output=argv[2];
        if(fs::exists(output))throw std::runtime_error("Output exists; refuse overwrite");
        std::ifstream source(input);if(!source)throw std::runtime_error("Cannot open input");
        Temporary temporary{output.string()+".tmp-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count())};
        if(fs::exists(temporary.path))throw std::runtime_error("Temporary name collision");
        std::ofstream destination(temporary.path);if(!destination)throw std::runtime_error("Cannot open temporary output");
        std::string line;if(!read_line(source,line))throw std::runtime_error("Missing header");if(!line.empty()&&line.back()=='\r')line.pop_back();
        if(line!="seq,time_ms,action,order_id,side,price_ticks,quantity")throw std::runtime_error("Unexpected header");
        destination<<"seq,time_ms,bid_ticks,ask_ticks,bid_qty,ask_qty,bid_top5,ask_top5,open_orders\n";
        Book book;I seq=0,lasttime=-1,count=0;const auto started=std::chrono::steady_clock::now();
        while(read_line(source,line)){
            if(!line.empty()&&line.back()=='\r')line.pop_back();
            if(line.size()>256)throw std::runtime_error("Row byte budget exceeded");
            if(++count>1000000)throw std::runtime_error("Event budget exceeded");
            try{
                auto fields=split(line);I current=integer(fields[0]),time=integer(fields[1]);
                if(current!=seq+1)throw std::runtime_error("Sequence gap or duplicate");
                if(time<0||time<lasttime)throw std::runtime_error("Timestamp regression");
                if(fields[2].size()!=1||fields[4].size()!=1)throw std::runtime_error("Action/side must be one character");
                book.apply(fields[2][0],integer(fields[3]),fields[4][0],integer(fields[5]),integer(fields[6]));
                book.snapshot(destination,current,time);seq=current;lasttime=time;
            }catch(const std::exception& exc){throw std::runtime_error("Event row "+std::to_string(count)+": "+exc.what());}
            if(!destination)throw std::runtime_error("Output write failed");
        }
        if(source.bad())throw std::runtime_error("Input read failed");
        if(count==0)throw std::runtime_error("No events");
        destination.flush();if(!destination)throw std::runtime_error("Output flush failed");destination.close();
        // Hard-link publication is create-only on Windows and POSIX; never replace a raced-in output.
        fs::create_hard_link(temporary.path,output);
        auto seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
        std::cout<<"{\"events\":"<<count<<",\"seconds\":"<<seconds<<",\"publication\":\"complete\"}\n";
        return 0;
    }catch(const std::exception& exc){std::cerr<<exc.what()<<'\n';return 2;}
}
